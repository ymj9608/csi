package com.csi;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import java.security.MessageDigest;

/** A scan owns its image snapshot and one visual assessment; coding reuses its instructions. */
@RestController
public class UnifiedReview {
 final Db db;
 public UnifiedReview(Db db){this.db=db;}
 static void snapshot(Db db,UUID scan,UUID project){
  var images=db.list("SELECT id,image,content_type FROM architecture_diagrams WHERE project_id=?",project);
  if(images.isEmpty())return; // Old projects remain readable; new scans explicitly fail without an image.
  var image=images.getFirst();byte[] bytes=(byte[])image.get("image");
  try {
   String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
   db.jdbc.update("INSERT INTO scan_visual_reviews(scan_id,diagram_id,image,content_type,image_sha256) VALUES(?,?,?,?,?)",scan,UUID.fromString(image.get("id").toString()),bytes,image.get("contentType"),sha);
  } catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
 }
 @GetMapping("/internal/scans/{id}/visual-input") public Object input(@PathVariable UUID id){
  var rows=db.list("SELECT v.diagram_id,v.image,v.content_type,v.image_sha256,s.commit_sha FROM scan_visual_reviews v JOIN scans s ON s.id=v.scan_id WHERE v.scan_id=?",id);
  if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.CONFLICT,"ARCHITECTURE_REQUIRED");
  db.jdbc.update("UPDATE architecture_diagrams d SET status='ANALYZING',error_code=null,updated_at=now() FROM scan_visual_reviews v WHERE v.scan_id=? AND v.result IS NULL AND d.id=v.diagram_id AND d.image=v.image AND d.status<>'ANALYZING' AND NOT EXISTS(SELECT 1 FROM scan_visual_reviews newer WHERE newer.diagram_id=v.diagram_id AND newer.created_at>v.created_at)",id);
  var row=new LinkedHashMap<>(rows.getFirst());row.put("imageBase64",Base64.getEncoder().encodeToString((byte[])row.remove("image")));return row;
 }
 static void require(boolean ok,String reason){if(!ok)throw new IllegalArgumentException(reason);}
 static void validate(JsonNode result,JsonNode snapshot,JsonNode reports,String commit){
  require("unified-vlm-review-v1".equals(result.path("mode").asText())&&result.toString().length()<150000,"Visual review schema");
  require(commit.equals(result.path("commitSha").asText())&&snapshot.path("diagramId").equals(result.path("diagramId"))&&snapshot.path("imageSha256").equals(result.path("imageSha256")),"Visual review identity");
  require(!result.path("model").asText().isBlank()&&result.path("model").asText().length()<=100,"Visual model required");
  var arch=result.path("architecture");
  require(arch.isObject()&&arch.size()==2&&arch.has("summary")&&arch.has("components"),"Visual architecture schema");
  try{ArchitectureController.validateResult(new com.fasterxml.jackson.databind.ObjectMapper().treeToValue(arch,ArchitectureController.Result.class));}catch(Exception e){throw new IllegalArgumentException("Visual architecture schema");}
  Map<String,Set<String>> refs=new HashMap<>();
  for(var report:reports){Set<String> ids=new HashSet<>();report.path("analysis").path("references").forEach(r->ids.add(r.path("chunkId").asText()));refs.put(report.path("id").asText(),ids);}
  var instructions=result.path("instructions");require(instructions.isArray()&&instructions.size()==refs.size(),"Visual instructions incomplete");
  Set<String> seen=new HashSet<>();
  for(var instruction:instructions){
   String id=instruction.path("findingId").asText(),text=instruction.path("text").asText();
   require(refs.containsKey(id)&&seen.add(id)&&text.strip().length()>=20&&text.length()<=3000&&!text.stripLeading().startsWith("{")&&!text.stripLeading().startsWith("[")&&!text.stripLeading().startsWith("```"),"Visual instruction invalid");
   var cites=instruction.path("referenceIds");require(cites.isArray()&&!cites.isEmpty()&&cites.size()<=8,"Visual instruction references required");
   for(var cite:cites)require(cite.isTextual()&&refs.get(id).contains(cite.asText()),"Visual instruction reference invalid");
  }
 }
 static void persist(Db db,UUID scan,JsonNode result,JsonNode reports,String commit){
  var row=db.one("SELECT diagram_id,image_sha256,result FROM scan_visual_reviews WHERE scan_id=? FOR UPDATE",scan);
  validate(result,db.json.valueToTree(row),reports,commit);
  if(row.get("result")!=null){require(db.json.valueToTree(row.get("result")).equals(result),"Visual review already finalized");return;}
  db.jdbc.update("UPDATE scan_visual_reviews SET result=?::jsonb,finished_at=now() WHERE scan_id=? AND result IS NULL",result.toString(),scan);
  // A scan must never replace the analysis of a newer upload.
  var arch=result.path("architecture");
  db.jdbc.update("UPDATE architecture_diagrams d SET status='EXTRACTED',components=?::jsonb,summary=?,error_code=null,updated_at=now() FROM scan_visual_reviews v WHERE v.scan_id=? AND d.id=v.diagram_id AND d.image=v.image AND NOT EXISTS(SELECT 1 FROM scan_visual_reviews newer WHERE newer.diagram_id=v.diagram_id AND newer.created_at>v.created_at)",arch.path("components").toString(),arch.path("summary").asText(),scan);
 }
 static void fail(Db db,UUID scan){
  db.jdbc.update("UPDATE architecture_diagrams d SET status='FAILED',error_code='WORKER_ERROR',updated_at=now() FROM scan_visual_reviews v WHERE v.scan_id=? AND d.id=v.diagram_id AND d.image=v.image AND v.result IS NULL AND NOT EXISTS(SELECT 1 FROM scan_visual_reviews newer WHERE newer.diagram_id=v.diagram_id AND newer.created_at>v.created_at)",scan);
 }
}
