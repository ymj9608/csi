package com.csi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.*;import org.springframework.web.multipart.MultipartFile;import org.springframework.web.server.ResponseStatusException;import org.springframework.http.*;import org.springframework.transaction.annotation.Transactional;import java.util.*;
@RestController public class ArchitectureController {
 final Db db;
 @Value("${CSI_ARCHITECTURE_JOB_TIMEOUT_SECONDS:2100}") int jobTimeoutSeconds=2100;
 static final Set<String> FAILURE_CODES=Set.of("MODEL_TIMEOUT","MODEL_UNAVAILABLE","INVALID_RESULT","BACKEND_UNAVAILABLE","WORKER_ERROR");
 public ArchitectureController(Db db){this.db=db;}
 @PostMapping("/api/projects/{id}/architecture") @Transactional public ResponseEntity<?> upload(@PathVariable UUID id,@RequestParam("file") MultipartFile file)throws Exception{
  db.one("SELECT id FROM projects WHERE id=?",id);
  var image=ArchitectureContexts.inspect(file);
  UUID diagramId=UUID.randomUUID();
  db.jdbc.update("INSERT INTO architecture_diagrams(id,project_id,image,content_type,status,components,summary,confirmed) VALUES(?,?,?,?,'QUEUED',null,null,false) ON CONFLICT(project_id) DO UPDATE SET id=EXCLUDED.id,image=EXCLUDED.image,content_type=EXCLUDED.content_type,status='QUEUED',components=null,summary=null,confirmed=false,error_code=null,updated_at=now()",diagramId,id,image.bytes(),image.contentType());
  return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id",diagramId,"status","QUEUED"));
 }
 @GetMapping("/api/projects/{id}/architecture") public Object get(@PathVariable UUID id){
  expireProject(id);
  return db.one("SELECT id,status,components,summary,confirmed,error_code FROM architecture_diagrams WHERE project_id=?",id);
 }
 private int timeoutSeconds(){return Math.max(60,Math.min(7200,jobTimeoutSeconds));}
 private void expireProject(UUID id){
  db.jdbc.update("UPDATE architecture_diagrams SET status='FAILED',error_code='WORKER_TIMEOUT',updated_at=now() WHERE project_id=? AND status IN ('LOADING_MODEL','ANALYZING') AND updated_at < now() - (? * interval '1 second')",id,timeoutSeconds());
 }
 @Scheduled(fixedDelay=30000) public void expire(){
  db.jdbc.update("UPDATE architecture_diagrams SET status='FAILED',error_code='WORKER_TIMEOUT',updated_at=now() WHERE status IN ('LOADING_MODEL','ANALYZING') AND updated_at < now() - (? * interval '1 second')",timeoutSeconds());
 }
 public record Retry(UUID diagramId){}
 @PostMapping("/api/projects/{id}/architecture/retry") @Transactional public Object retry(@PathVariable UUID id,@RequestBody Retry request){
  if(request.diagramId()==null)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Missing diagramId");
  UUID next=UUID.randomUUID();
  int updated=db.jdbc.update("UPDATE architecture_diagrams SET id=?,status='QUEUED',error_code=null,components=null,summary=null,confirmed=false,updated_at=now() WHERE project_id=? AND id=? AND status='FAILED'",next,id,request.diagramId());
  if(updated==0)throw new ResponseStatusException(HttpStatus.CONFLICT,"실패한 최신 분석만 다시 요청할 수 있습니다.");
  return Map.of("id",next,"status","QUEUED");
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
 public record Failure(String errorCode){}
 @PostMapping("/internal/architecture/{id}/failure") @Transactional public Object failure(@PathVariable UUID id,@RequestBody Failure request){
  if(request.errorCode()==null||!FAILURE_CODES.contains(request.errorCode()))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid error code");
  int updated=db.jdbc.update("UPDATE architecture_diagrams SET status='FAILED',error_code=?,updated_at=now() WHERE id=? AND status IN ('LOADING_MODEL','ANALYZING')",request.errorCode(),id);
  if(updated==0){
   var row=db.one("SELECT status FROM architecture_diagrams WHERE id=?",id);
   if(!"FAILED".equals(row.get("status")))throw new ResponseStatusException(HttpStatus.CONFLICT,"Analysis is no longer running");
  }
  return Map.of("status","FAILED");
 }
 static void validateResult(Result result){
  if(result==null||result.summary()==null||result.summary().isBlank()||result.summary().length()>180)throw new IllegalArgumentException("Invalid summary");
  if(result.components()==null||result.components().isEmpty()||result.components().size()>6)throw new IllegalArgumentException("Invalid components");
  for(var c:result.components()){
   if(c==null||c.name()==null||c.name().isBlank()||c.name().length()>60||c.role()==null||c.role().isBlank()||c.role().length()>40)throw new IllegalArgumentException("Invalid component field");
   if(c.isolationStatus()==null||!Set.of("ISOLATED","PRODUCTION","UNKNOWN").contains(c.isolationStatus()))throw new IllegalArgumentException("Invalid isolationStatus");
   if(c.state()==null||!Set.of("OBSERVED","INFERRED","UNKNOWN").contains(c.state()))throw new IllegalArgumentException("Invalid state");
  }
 }
 @PostMapping("/internal/architecture/{id}/result") @Transactional public Object result(@PathVariable UUID id,@RequestBody Result result){
  try{validateResult(result);}catch(IllegalArgumentException e){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,e.getMessage());}
  int updated=db.jdbc.update("UPDATE architecture_diagrams SET status='EXTRACTED',components=?::jsonb,summary=?,error_code=null,updated_at=now() WHERE id=? AND status='ANALYZING'",db.encode(result.components()),result.summary(),id);
  if(updated==0)throw new ResponseStatusException(HttpStatus.CONFLICT,"Analysis is no longer running");
  return Map.of("status","EXTRACTED");
 }
}
