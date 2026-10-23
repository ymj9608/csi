package com.csi;
import org.springframework.web.bind.annotation.*;import org.springframework.web.multipart.MultipartFile;import org.springframework.web.server.ResponseStatusException;import org.springframework.http.*;import org.springframework.transaction.annotation.Transactional;import java.util.*;
@RestController public class ArchitectureController {
 final Db db;
 public ArchitectureController(Db db){this.db=db;}
 @PostMapping("/api/projects/{id}/architecture") @Transactional public ResponseEntity<?> upload(@PathVariable UUID id,@RequestParam("file") MultipartFile file)throws Exception{
  db.one("SELECT id FROM projects WHERE id=?",id);
  UUID diagramId=UUID.randomUUID();
  db.jdbc.update("INSERT INTO architecture_diagrams(id,project_id,image,content_type,status,components,summary,confirmed) VALUES(?,?,?,?,'QUEUED',null,null,false) ON CONFLICT(project_id) DO UPDATE SET id=EXCLUDED.id,image=EXCLUDED.image,content_type=EXCLUDED.content_type,status='QUEUED',components=null,summary=null,confirmed=false,updated_at=now()",diagramId,id,file.getBytes(),file.getContentType());
  return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id",diagramId,"status","QUEUED"));
 }
 @GetMapping("/api/projects/{id}/architecture") public Object get(@PathVariable UUID id){
  return db.one("SELECT status,components,summary,confirmed FROM architecture_diagrams WHERE project_id=?",id);
 }
 @PostMapping("/internal/projects/{id}/architecture/claim") @Transactional public ResponseEntity<?> claim(@PathVariable UUID id){
  var rows=db.list("SELECT id FROM architecture_diagrams WHERE project_id=? AND status='QUEUED' FOR UPDATE SKIP LOCKED",id);
  if(rows.isEmpty())return ResponseEntity.noContent().build();
  UUID diagramId=UUID.fromString((String)rows.getFirst().get("id"));
  db.jdbc.update("UPDATE architecture_diagrams SET status='LOADING_MODEL',updated_at=now() WHERE id=?",diagramId);
  return ResponseEntity.ok(Map.of("diagramId",diagramId));
 }
 public record Progress(String phase){}
 @PostMapping("/internal/architecture/{id}/progress") @Transactional public Object progress(@PathVariable UUID id,@RequestBody Progress progress){
  if(!"ANALYZING".equals(progress.phase()))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid phase");
  int updated=db.jdbc.update("UPDATE architecture_diagrams SET status='ANALYZING',updated_at=now() WHERE id=? AND status='LOADING_MODEL'",id);
  if(updated==0)throw new ResponseStatusException(HttpStatus.CONFLICT,"잘못된 상태 전이입니다.");
  return Map.of("status","ANALYZING");
 }
 @GetMapping("/internal/architecture/{id}/image") public ResponseEntity<byte[]> image(@PathVariable UUID id){
  var row=db.one("SELECT image,content_type FROM architecture_diagrams WHERE id=?",id);
  return ResponseEntity.ok().contentType(MediaType.parseMediaType((String)row.get("contentType"))).body((byte[])row.get("image"));
 }
 public record Component(String name,String role,String isolationStatus,String state){}
 public record Result(List<Component> components,String summary){}
 static void validateResult(Result result){
  if(result.summary()==null||result.summary().isBlank())throw new IllegalArgumentException("Missing summary");
  if(result.components()==null||result.components().isEmpty())throw new IllegalArgumentException("Missing components");
  for(var c:result.components()){
   if(c.name()==null||c.name().isBlank()||c.role()==null||c.role().isBlank())throw new IllegalArgumentException("Missing component field");
   if(!Set.of("ISOLATED","PRODUCTION","UNKNOWN").contains(c.isolationStatus()))throw new IllegalArgumentException("Invalid isolationStatus");
   if(!Set.of("OBSERVED","INFERRED","UNKNOWN").contains(c.state()))throw new IllegalArgumentException("Invalid state");
  }
 }
 @PostMapping("/internal/architecture/{id}/result") @Transactional public Object result(@PathVariable UUID id,@RequestBody Result result){
  try{validateResult(result);}catch(IllegalArgumentException e){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,e.getMessage());}
  db.jdbc.update("UPDATE architecture_diagrams SET status='EXTRACTED',components=?::jsonb,summary=?,updated_at=now() WHERE id=?",db.encode(result.components()),result.summary(),id);
  return Map.of("status","EXTRACTED");
 }
}
