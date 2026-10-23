package com.csi;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;

/** Versioned, unverified architecture hints. This controller never changes scan scope or findings. */
@RestController
public class ArchitectureContexts {
 static final int MAX_BYTES=5*1024*1024, MAX_PIXELS=16_000_000, MAX_EDGE=8192;
 static final String SELECT="SELECT a.id,a.project_id,a.version,a.image_sha256,a.image_content_type,a.image_width,a.image_height,a.model,a.prompt_version,a.source_commit_sha,a.status,a.lease_token,a.lease_until,a.result,a.error_code,a.created_by,a.created_at,a.finished_at,p.repository FROM project_architectures a JOIN projects p ON p.id=a.project_id ";
 final Db db;
 final String model, promptVersion;

 public ArchitectureContexts(Db db,
  @Value("${CSI_ARCHITECTURE_MODEL:ministral-3:8b-instruct-2512-q4_K_M}") String model,
  @Value("${CSI_ARCHITECTURE_PROMPT_VERSION:architecture-v1}") String promptVersion){
  this.db=db;this.model=model;this.promptVersion=promptVersion;
 }

 record ImageInfo(byte[] bytes,String contentType,int width,int height,String sha256){}
 static ImageInfo inspect(MultipartFile file){
  if(file==null || file.isEmpty() || file.getSize()>MAX_BYTES)
   throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"PNG/JPEG 이미지는 5 MiB 이하여야 합니다.");
  try {
   // Bound reads independently of the client-supplied length and reject image decompression bombs.
   byte[] bytes;
   try(var input=file.getInputStream()){bytes=input.readNBytes(MAX_BYTES+1);}
   if(bytes.length==0 || bytes.length>MAX_BYTES)throw new IOException("Image size");
   try(var stream=new MemoryCacheImageInputStream(new ByteArrayInputStream(bytes))){
    var readers=ImageIO.getImageReaders(stream);
    if(!readers.hasNext())throw new IOException("Unsupported image");
    var reader=readers.next();
    try {
     String format=reader.getFormatName().toLowerCase(Locale.ROOT);
     if(!Set.of("png","jpeg","jpg").contains(format))throw new IOException("Unsupported image");
     String type=format.equals("png")?"image/png":"image/jpeg";
     if(!type.equals(file.getContentType()))throw new IOException("Image content type mismatch");
     reader.setInput(stream,true,true);
     int width=reader.getWidth(0),height=reader.getHeight(0);
     if(width<1 || height<1 || width>MAX_EDGE || height>MAX_EDGE || (long)width*height>MAX_PIXELS)throw new IOException("Image dimensions");
     if(reader.read(0)==null)throw new IOException("Invalid image");
     return new ImageInfo(bytes,type,width,height,HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
    } finally {reader.dispose();}
   }
  } catch(Exception e){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"유효한 PNG/JPEG 이미지(최대 16 MP, 가로·세로 각각 8192 px)가 필요합니다.");}
 }

 static Map<String,Object> publicJob(Map<String,Object> row){
  var result=new LinkedHashMap<>(row);
  result.remove("imageBytes");result.remove("leaseToken");result.remove("leaseUntil");
  return result;
 }
 static String commit(String value){
  String result=value==null?"":value;
  if(!result.isEmpty() && !result.matches("[a-f0-9]{40}"))
   throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"sourceCommitSha는 40자리 소문자 Git SHA여야 합니다.");
  return result;
 }
 @PostMapping(value="/api/projects/{projectId}/architectures",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
 @Transactional public Object upload(@PathVariable UUID projectId,@RequestPart("file") MultipartFile file,
    @RequestParam(required=false) String sourceCommitSha,Authentication auth){
  String source=commit(sourceCommitSha);
  var image=inspect(file);
  // Project lock serializes version allocation and identical concurrent uploads.
  db.one("SELECT id FROM projects WHERE id=? FOR UPDATE",projectId);
  var cached=db.list(SELECT+"WHERE a.project_id=? AND a.image_sha256=? AND a.model=? AND a.prompt_version=? AND a.source_commit_sha=?",projectId,image.sha256(),model,promptVersion,source);
  if(!cached.isEmpty()){
   var result=publicJob(cached.getFirst());result.put("reused",true);return result;
  }
  UUID id=UUID.randomUUID();
  long version=db.count("SELECT coalesce(max(version),0)+1 FROM project_architectures WHERE project_id=?",projectId);
  db.jdbc.update("INSERT INTO project_architectures(id,project_id,version,image_sha256,image_content_type,image_width,image_height,image_bytes,model,prompt_version,source_commit_sha,status,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED',?)",
   id,projectId,version,image.sha256(),image.contentType(),image.width(),image.height(),image.bytes(),model,promptVersion,source,auth.getName());
  var result=publicJob(db.one(SELECT+"WHERE a.id=?",id));result.put("reused",false);return result;
 }
 /** Explicit image choice for direct VLM handoff, independent of graph extraction status. */
 @PostMapping("/api/projects/{projectId}/architectures/{id}/select-for-coding") @Transactional
 public Object selectForCoding(@PathVariable UUID projectId,@PathVariable UUID id){
  db.one("SELECT id FROM projects WHERE id=? FOR UPDATE",projectId);
  db.one("SELECT id FROM project_architectures WHERE project_id=? AND id=?",projectId,id);
  db.jdbc.update("UPDATE projects SET coding_architecture_id=? WHERE id=?",id,projectId);
  return Map.of("architectureId",id,"selected",true);
 }
 @GetMapping("/api/projects/{projectId}/architectures") public Object list(@PathVariable UUID projectId){
  db.one("SELECT id FROM projects WHERE id=?",projectId);
  return Map.of("items",db.list(SELECT+"WHERE a.project_id=? ORDER BY version DESC LIMIT 50",projectId).stream().map(ArchitectureContexts::publicJob).toList(),"advisoryOnly",true);
 }
 @GetMapping("/api/projects/{projectId}/architectures/{id}") public Object get(@PathVariable UUID projectId,@PathVariable UUID id){
  return publicJob(db.one(SELECT+"WHERE a.project_id=? AND a.id=?",projectId,id));
 }
 @GetMapping("/api/projects/{projectId}/architectures/{id}/image") public ResponseEntity<byte[]> image(@PathVariable UUID projectId,@PathVariable UUID id){
  var row=db.one("SELECT image_bytes,image_content_type FROM project_architectures WHERE project_id=? AND id=?",projectId,id);
  return ResponseEntity.ok().contentType(MediaType.parseMediaType((String)row.get("imageContentType")))
   .header("X-Content-Type-Options","nosniff").header("Cache-Control","private, no-store")
   .body((byte[])row.get("imageBytes"));
 }
 @GetMapping({"/api/projects/{projectId}/architecture-context","/internal/projects/{projectId}/architecture-context"})
 public Object context(@PathVariable UUID projectId,@RequestParam(required=false) String commitSha){
  String current=commit(commitSha);db.one("SELECT id FROM projects WHERE id=?",projectId);
  var rows=db.list(SELECT+"WHERE a.project_id=? ORDER BY version DESC LIMIT 1",projectId);
  return contextResponse(rows.isEmpty()?null:rows.getFirst(),current);
 }
 static Map<String,Object> contextResponse(Map<String,Object> latest,String current){
  var out=new LinkedHashMap<String,Object>();
  out.put("available",latest!=null && "READY".equals(latest.get("status")));
  out.put("status",latest==null?"NOT_PROVIDED":latest.get("status"));
  out.put("advisoryOnly",true);out.put("codeVerificationRequired",true);
  String source=latest==null?"":Objects.toString(latest.get("sourceCommitSha"),"");
  Boolean matches=current.isEmpty() || source.isEmpty()?null:source.equals(current);
  out.put("sourceCommitMatches",matches);
  out.put("staleness",matches==null?"UNKNOWN":matches?"MATCHED":"COMMIT_MISMATCH");
  out.put("architecture",latest==null?null:publicJob(latest));return out;
 }
 @PostMapping("/api/projects/{projectId}/architectures/{id}/retry") @Transactional
 public Object retry(@PathVariable UUID projectId,@PathVariable UUID id){
  var row=db.one(SELECT+"WHERE a.project_id=? AND a.id=? FOR UPDATE OF a",projectId,id);
  if(!"FAILED".equals(row.get("status")))throw new ResponseStatusException(HttpStatus.CONFLICT,"실패한 분석만 재요청할 수 있습니다.");
  if(!model.equals(row.get("model")) || !promptVersion.equals(row.get("promptVersion")))
   throw new ResponseStatusException(HttpStatus.CONFLICT,"모델 또는 프롬프트 설정이 변경되었습니다. 같은 이미지를 다시 업로드하여 현재 설정의 새 버전을 생성하세요.");
  db.jdbc.update("UPDATE project_architectures SET status='QUEUED',error_code=null,result=null,lease_token=null,lease_until=null,finished_at=null WHERE id=?",id);
  return publicJob(db.one(SELECT+"WHERE a.id=?",id));
 }

 public record Claim(String model,String promptVersion){}
 @PostMapping("/internal/architectures/claim") @Transactional public Object claim(@RequestBody Claim claim){
  if(!model.equals(claim.model()) || !promptVersion.equals(claim.promptVersion()))
   throw new ResponseStatusException(HttpStatus.CONFLICT,"Architecture worker model/prompt mismatch");
  var rows=db.list("SELECT id FROM project_architectures WHERE status='QUEUED' AND model=? AND prompt_version=? ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED",model,promptVersion);
  if(rows.isEmpty())return Map.of("available",false);
  UUID id=UUID.fromString((String)rows.getFirst().get("id")),token=UUID.randomUUID();
  db.jdbc.update("UPDATE project_architectures SET status='RUNNING',lease_token=?,lease_until=now()+interval '10 minutes' WHERE id=?",token,id);
  var job=new LinkedHashMap<>(db.one(SELECT+"WHERE a.id=?",id));
  byte[] bytes=(byte[])db.one("SELECT image_bytes FROM project_architectures WHERE id=?",id).get("imageBytes");
  job.put("imageBase64",Base64.getEncoder().encodeToString(bytes));
  return Map.of("available",true,"job",job);
 }
 @GetMapping("/internal/architectures/{id}") public Object internal(@PathVariable UUID id){
  var row=new LinkedHashMap<>(db.one(SELECT+"WHERE a.id=?",id));row.remove("imageBytes");return row;
 }
 void requireLease(UUID id,String token,Map<String,Object> row){
  if(token==null || token.isBlank() || !"RUNNING".equals(row.get("status")) || !token.equals(row.get("leaseToken")) ||
   db.count("SELECT count(*) FROM project_architectures WHERE id=? AND lease_until>now()",id)!=1)
   throw new ResponseStatusException(HttpStatus.CONFLICT,"만료되었거나 이미 처리된 아키텍처 분석입니다.");
 }
 @PostMapping("/internal/architectures/{id}/result") @Transactional public Object complete(@PathVariable UUID id,@RequestBody JsonNode body){
  var row=db.one(SELECT+"WHERE a.id=? FOR UPDATE OF a",id);
  String token=body.path("leaseToken").asText();JsonNode result=body.path("result");
  if("READY".equals(row.get("status")) && !token.isBlank() && token.equals(row.get("leaseToken")) && result.equals(db.json.valueToTree(row.get("result"))))
   return Map.of("status","READY","replayed",true);
  requireLease(id,token,row);
  try{validateResult(result,row);}catch(IllegalArgumentException e){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,e.getMessage());}
  db.jdbc.update("UPDATE project_architectures SET status='READY',result=?::jsonb,finished_at=now(),lease_until=null WHERE id=?",result.toString(),id);
  return Map.of("status","READY","replayed",false);
 }
 public record Failure(String leaseToken,String errorCode){}
 @PostMapping("/internal/architectures/{id}/failure") @Transactional public Object fail(@PathVariable UUID id,@RequestBody Failure failure){
  var row=db.one(SELECT+"WHERE a.id=? FOR UPDATE OF a",id);
  String code=failure.errorCode();if(code==null || !code.matches("[A-Z_]{1,80}"))code="WORKER_FAILED";
  if("FAILED".equals(row.get("status")) && failure.leaseToken()!=null && failure.leaseToken().equals(row.get("leaseToken")) && code.equals(row.get("errorCode")))
   return Map.of("status","FAILED","replayed",true);
  requireLease(id,failure.leaseToken(),row);
  db.jdbc.update("UPDATE project_architectures SET status='FAILED',error_code=?,finished_at=now(),lease_until=null WHERE id=?",code,id);
  return Map.of("status","FAILED","replayed",false);
 }
 @Scheduled(fixedDelay=30000) public void expire(){
  db.jdbc.update("UPDATE project_architectures SET status='FAILED',error_code='MODEL_OR_PROMPT_CHANGED',finished_at=now(),lease_token=null,lease_until=null WHERE status='QUEUED' AND (model<>? OR prompt_version<>?)",model,promptVersion);
  db.jdbc.update("UPDATE project_architectures SET status='FAILED',error_code='WORKER_LEASE_EXPIRED',finished_at=now(),lease_token=null,lease_until=null WHERE status='RUNNING' AND lease_until<now()");
 }

 static void keys(JsonNode value,Set<String> expected){
  if(!value.isObject())throw new IllegalArgumentException("Object required");
  var keys=new HashSet<String>();value.fieldNames().forEachRemaining(keys::add);
  if(!keys.equals(expected))throw new IllegalArgumentException("Unexpected or missing architecture fields");
 }
 static String text(JsonNode value,int max){
  if(!value.isTextual() || value.asText().isBlank() || value.asText().length()>max)throw new IllegalArgumentException("Invalid architecture text");
  return value.asText();
 }
 static void array(JsonNode value,int max){
  if(!value.isArray() || value.size()>max)throw new IllegalArgumentException("Invalid architecture array");
 }
 static void strings(JsonNode value,int count,int max){array(value,count);value.forEach(v->text(v,max));}
 static void validateResult(JsonNode result,Map<String,Object> job){
  if(result.toString().length()>150000)throw new IllegalArgumentException("Architecture result too large");
  keys(result,Set.of("schemaVersion","imageSha256","model","promptVersion","diagramType","components","flows","trustBoundaries","codeHints","assumptions","uncertainties","summary","metrics"));
  if(!result.path("schemaVersion").isInt() || result.path("schemaVersion").asInt()!=1)throw new IllegalArgumentException("Architecture schema version");
  for(String key:List.of("imageSha256","model","promptVersion"))
   if(!Objects.equals(job.get(key),result.path(key).asText()))throw new IllegalArgumentException("Architecture identity mismatch");
  if(!Set.of("ARCHITECTURE","WORKFLOW","UNKNOWN").contains(result.path("diagramType").asText()))throw new IllegalArgumentException("Architecture diagram type");
  text(result.path("summary"),2000);
  var components=result.path("components");array(components,64);var ids=new HashSet<String>();
  for(var component:components){
   keys(component,Set.of("id","label","kind"));
   if(!ids.add(text(component.path("id"),64)))throw new IllegalArgumentException("Duplicate architecture component");
   text(component.path("label"),160);text(component.path("kind"),80);
  }
  var flows=result.path("flows");array(flows,128);
  for(var flow:flows){
   keys(flow,Set.of("from","to","data","protection"));
   if(!ids.contains(flow.path("from").asText()) || !ids.contains(flow.path("to").asText()))throw new IllegalArgumentException("Unknown architecture component");
   text(flow.path("data"),500);text(flow.path("protection"),500);
  }
  strings(result.path("trustBoundaries"),64,500);strings(result.path("assumptions"),64,500);strings(result.path("uncertainties"),64,500);
  strings(result.path("codeHints"),64,300);
  for(var hint:result.path("codeHints")){
   String value=hint.asText();
   if(value.startsWith("/") || value.contains("\\") || value.contains(":") || Arrays.asList(value.split("/",-1)).contains("..") || value.indexOf('\0')>=0)
    throw new IllegalArgumentException("Unsafe architecture code hint");
  }
  var metrics=result.path("metrics");
  if(!metrics.isObject() || metrics.size()>30)throw new IllegalArgumentException("Invalid architecture metrics");
  metrics.fields().forEachRemaining(entry->{
   if(!entry.getKey().matches("[a-zA-Z][a-zA-Z0-9_]{0,63}") || !entry.getValue().isNumber() || !Double.isFinite(entry.getValue().asDouble()) || entry.getValue().asDouble()<0)
    throw new IllegalArgumentException("Invalid architecture metric");
  });
 }
}
