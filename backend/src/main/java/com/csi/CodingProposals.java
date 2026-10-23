package com.csi;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

@RestController
public class CodingProposals {
 static final String TARGET="backend/app/core/csi_signup.py";
 static final String MODEL="ministral-3:8b-instruct-2512-q4_K_M";
 static final Set<String> SECURITY_TESTS=Set.of(
  "test_no_sensitive_logs","test_password_hash_is_bcrypt_cost12","test_per_password_random_salt",
  "test_new_hash_correct_and_wrong_password","test_old_lab_accounts_still_login_only_in_lab_mode",
  "test_synthetic_input_guard_remains","test_full_signup_storage_logs_login","test_password_inputs_round_trip",
  "test_new_hash_login_outside_lab_mode","test_password_length_limit","test_sensitive_logs_for_varied_inputs",
  "test_legacy_hash_rejects_malformed_values","test_legacy_login_keeps_existing_hash_before_migration");
 static final String SELECT="SELECT c.*,s.repository,s.commit_sha,s.project_id FROM coding_proposals c JOIN scans s ON s.id=c.scan_id ";
 final Db db; final Events events; final boolean enabled; final Set<String> repositories;
 @Value("${CSI_VLM_PROVIDER:openai}") String vlmProvider="openai";
 @Value("${CSI_VLM_MODEL:}") String vlmModel="";
 String configuredVlmModel(){return vlmModel.isBlank()?("ollama".equals(vlmProvider)?"qwen3-vl:8b":"gpt-5.4-mini-2026-03-17"):vlmModel;}
 public CodingProposals(Db db,Events events,@Value("${CSI_CODING_ENABLED:false}")boolean enabled,
                        @Value("${CSI_CODING_REPOSITORIES:ymj9608/Lichu}")String repositories){
  this.db=db;this.events=events;this.enabled=enabled;this.repositories=Set.of(repositories.split(","));
 }
 @GetMapping("/api/scans/{id}/coding-proposals") public Object list(@PathVariable UUID id){
  var scan=db.one("SELECT repository,status FROM scans WHERE id=?",id);
  boolean supported=repositories.contains(scan.get("repository")) && applicable(id);
  var items=db.list(SELECT+"WHERE scan_id=? ORDER BY c.created_at DESC LIMIT 20",id);
  return Map.of("enabled",enabled,"supported",supported,"orchestratorModel",configuredVlmModel(),"orchestratorProvider",vlmProvider,"architectureRequired",false,"items",items.stream().map(CodingProposals::publicJob).toList());
 }
 static Map<String,Object> publicJob(Map<String,Object> job){
  var visible=new LinkedHashMap<>(job);visible.remove("leaseToken");visible.remove("leaseUntil");return visible;
 }
 boolean applicable(UUID scan){return db.count("SELECT count(*) FROM findings WHERE scan_id=? AND file_path=? AND rule_id IN ('SEC-02','SEC-03','SEC-05')",scan,TARGET)>0;}
 @PostMapping("/api/scans/{id}/coding-proposals") @Transactional public Object request(@PathVariable UUID id){return queue(id,true);}
 @Transactional public Map<String,Object> queue(UUID id,boolean explicit){
  var scan=db.one("SELECT * FROM scans WHERE id=? FOR UPDATE",id);
  if(!enabled || !repositories.contains(scan.get("repository")) || !"COMPLETED".equals(scan.get("status")) || !applicable(id)){
   if(explicit)throw new ResponseStatusException(HttpStatus.CONFLICT,"완료된 Lichu 실습 검사와 코딩 Agent 활성화가 필요합니다.");
   return Map.of();
  }
  var existing=db.list(SELECT+"WHERE scan_id=? AND c.status IN ('QUEUED','RUNNING','READY','APPROVED')",id);
  if(!existing.isEmpty())return publicJob(existing.getFirst());
  var images=db.list("SELECT a.id,a.source_commit_sha FROM projects p JOIN project_architectures a ON a.id=p.coding_architecture_id AND a.project_id=p.id WHERE p.id=?",UUID.fromString((String)scan.get("projectId")));
  var image=images.isEmpty()?Map.<String,Object>of():images.getFirst();String source=Objects.toString(image.get("sourceCommitSha"),"");
  if(!source.isEmpty() && !source.equals(scan.get("commitSha"))){
   if(explicit)throw new ResponseStatusException(HttpStatus.CONFLICT,"아키텍처의 기준 커밋이 검사 커밋과 다릅니다. 현재 검사에 맞는 이미지를 연결하세요.");
   return Map.of();
  }
  UUID proposal=UUID.randomUUID();
  db.jdbc.update("INSERT INTO coding_proposals(id,scan_id,status,architecture_id) VALUES(?,?,'QUEUED',?)",proposal,id,image.isEmpty()?null:UUID.fromString((String)image.get("id")));
  db.log(id,"CODING_QUEUED","coding-agent","INFO","Local coding proposal queued for immutable scan commit");events.publish(id.toString());
  return publicJob(db.one(SELECT+"WHERE c.id=?",proposal));
 }
 public record Claim(String repository){}
 @PostMapping("/internal/coding-proposals/claim") @Transactional public Object claim(@RequestBody Claim claim){
  if(!enabled || !repositories.contains(claim.repository()))throw new ResponseStatusException(HttpStatus.FORBIDDEN);
  var rows=db.list("SELECT c.id FROM coding_proposals c JOIN scans s ON s.id=c.scan_id WHERE c.status='QUEUED' AND s.repository=? ORDER BY c.created_at LIMIT 1 FOR UPDATE OF c SKIP LOCKED",claim.repository());
  if(rows.isEmpty())return Map.of("available",false);
  UUID id=UUID.fromString((String)rows.getFirst().get("id")),token=UUID.randomUUID();
  db.jdbc.update("UPDATE coding_proposals SET status='RUNNING',lease_token=?,lease_until=now()+interval '15 minutes' WHERE id=?",token,id);
  var job=db.one(SELECT+"WHERE c.id=?",id);UUID scan=UUID.fromString((String)job.get("scanId"));
  job.put("policy",db.one("SELECT policy FROM scans WHERE id=?",scan).get("policy"));
  job.put("findings",db.list("SELECT id,rule_id,file_path,title,category,analysis FROM findings WHERE scan_id=? AND file_path=?",scan,TARGET));
  job.put("vlmModel",configuredVlmModel());job.put("vlmProvider",vlmProvider);
  job.put("architectureDiagram",architectureDiagram(job));
  if(job.get("architectureId")!=null){
   var image=new LinkedHashMap<>(db.one("SELECT a.id,a.version,a.image_sha256,a.image_content_type,a.source_commit_sha,a.image_bytes FROM project_architectures a JOIN scans s ON s.project_id=a.project_id WHERE a.id=? AND s.id=?",UUID.fromString((String)job.get("architectureId")),scan));
   image.put("imageBase64",Base64.getEncoder().encodeToString((byte[])image.remove("imageBytes")));
   job.put("architecture",image);
  }
  db.log(scan,"CODING_RUNNING","coding-agent","INFO","Local worker claimed coding proposal");events.publish(scan.toString());
  return Map.of("available",true,"job",job);
 }
 @GetMapping("/internal/coding-proposals/{id}") public Object internal(@PathVariable UUID id){return db.one(SELECT+"WHERE c.id=?",id);}
 Map<String,Object> architectureDiagram(Map<String,Object> job){
  // Only completed extraction for this scan's project; never borrow another project's diagram.
  String sql="SELECT d.id,d.project_id,d.status,d.components,d.summary,d.confirmed,d.updated_at FROM architecture_diagrams d WHERE d.project_id=? AND d.status='EXTRACTED'";
  UUID project=UUID.fromString((String)job.get("projectId"));
  List<Map<String,Object>> rows;
  if(job.get("architectureId")!=null){
   rows=db.list(sql+" AND EXISTS (SELECT 1 FROM project_architectures a WHERE a.id=? AND a.project_id=d.project_id AND a.image_bytes=d.image)",project,UUID.fromString((String)job.get("architectureId")));
  }else rows=db.list(sql,project);
  return rows.isEmpty()?Map.of():rows.getFirst();
 }
 public record Progress(String leaseToken,String phase,int attempt,long elapsedMs,String note){
  public Progress(String leaseToken,String phase,int attempt,long elapsedMs){this(leaseToken,phase,attempt,elapsedMs,null);}
 }
 static void validateProgress(Progress progress){
  if(!Set.of("ARCHITECTURE_CONTEXT","VLM_PLANNING","VLM_READING","BASELINE","GENERATING","VALIDATING","VERIFYING","RETRYING").contains(String.valueOf(progress.phase())) ||
     progress.attempt()<0 || progress.attempt()>2 || progress.elapsedMs()<0 || progress.elapsedMs()>900000 ||
     (progress.note()!=null && progress.note().length()>200))
   throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid coding progress");
 }
 @PostMapping("/internal/coding-proposals/{id}/progress") @Transactional public Object progress(@PathVariable UUID id,@RequestBody Progress progress){
  validateProgress(progress);var job=leased(id,progress.leaseToken());
  var fields=new LinkedHashMap<String,Object>();
  fields.put("phase",progress.phase());fields.put("attempt",progress.attempt());fields.put("elapsedMs",progress.elapsedMs());
  if(progress.note()!=null)fields.put("note",progress.note());
  if("ARCHITECTURE_CONTEXT".equals(progress.phase()) && progress.note()!=null)fields.put("architectureNote",progress.note());
  String value=db.encode(fields);
  db.jdbc.update("UPDATE coding_proposals SET progress=coalesce(progress,'{}'::jsonb)-'note' || ?::jsonb || jsonb_build_object('updatedAt',now()) WHERE id=?",value,id);
  events.publish((String)job.get("scanId"));return Map.of("status","RUNNING");
 }
 Map<String,Object> leased(UUID id,String token){
  var row=db.one(SELECT+"WHERE c.id=? FOR UPDATE OF c",id);
  requireLease(id,token,row);return row;
 }
 void requireLease(UUID id,String token,Map<String,Object> row){
  if(token==null || token.isBlank() || !"RUNNING".equals(row.get("status")) || !Objects.equals(token,row.get("leaseToken")) ||
     db.count("SELECT count(*) FROM coding_proposals WHERE id=? AND lease_until>now()",id)!=1)
   throw new ResponseStatusException(HttpStatus.CONFLICT,"만료되었거나 이미 처리된 작업입니다.");
 }
 static void validateResult(JsonNode result,Map<String,Object> job,Set<String> findings,Set<String> references){
  if(result.toString().length()>150000 || result.path("schemaVersion").asInt()!=1 || !Set.of("3","4").contains(result.path("engineVersion").asText()) || !"lichu-signup-v1".equals(result.path("profile").asText()) ||
    !Objects.equals(job.get("commitSha"),result.path("commitSha").asText()) || !Objects.equals(job.get("repository"),result.path("repository").asText()) || !MODEL.equals(result.path("model").asText()))throw new IllegalArgumentException("Coding context mismatch");
  if(job.get("architectureId")!=null){
   var handoff=result.path("handoff");
   if(!"4".equals(result.path("engineVersion").asText()) || !"vlm-orchestrator-v1".equals(handoff.path("mode").asText()) ||
      !("openai".equals(handoff.path("provider").asText()) && Set.of("gpt-6.1-sol","gpt-6-astra","gpt-5.4-mini","gpt-5.4-mini-2026-03-17").contains(handoff.path("model").asText()) ||
        "ollama".equals(handoff.path("provider").asText()) && "qwen3-vl:8b".equals(handoff.path("model").asText())) ||
      !Objects.equals(job.get("architectureId"),handoff.path("architectureId").asText()) ||
      !Objects.equals(job.get("commitSha"),handoff.path("commitSha").asText()) ||
      !result.path("status").asText().equals(handoff.path("status").asText()) ||
      !handoff.path("imageSha256").asText().matches("[a-f0-9]{64}") ||
      handoff.path("instruction").asText().length()>6000 || handoff.path("conclusion").asText().length()>3000)
    throw new IllegalArgumentException("VLM orchestration required");
   var trace=handoff.path("trace");
   if(!trace.isArray() || trace.size()>14)throw new IllegalArgumentException("VLM trace required");
   for(String metric:List.of("inputTokens","outputTokens","wallDurationMs"))
    if(!handoff.path("metrics").path(metric).isIntegralNumber() || handoff.path("metrics").path(metric).asLong()<0)
     throw new IllegalArgumentException("VLM usage required");
   if("READY".equals(result.path("status").asText())){
    boolean delegated=false,checked=false;
    for(var step:trace)if("OK".equals(step.path("status").asText())){
     if("delegate_coding".equals(step.path("tool").asText())){delegated=true;checked=false;}
     if("run_verification".equals(step.path("tool").asText()) && delegated)checked=true;
    }
    if(!delegated || !checked || trace.isEmpty() || !"finish_review".equals(trace.get(trace.size()-1).path("tool").asText()) ||
       !"OK".equals(trace.get(trace.size()-1).path("status").asText()) || handoff.path("instruction").asText().isBlank() || handoff.path("conclusion").asText().isBlank())
     throw new IllegalArgumentException("VLM verified review required");
   }
  }else if(!"3".equals(result.path("engineVersion").asText())){
   throw new IllegalArgumentException("Image required for orchestration");
  }
  String status=result.path("status").asText();if(!Set.of("READY","BLOCKED").contains(status))throw new IllegalArgumentException("Coding status");
  for(var f:result.path("findingIds"))if(!findings.contains(f.asText()))throw new IllegalArgumentException("Unknown finding");
  for(var r:result.path("referenceIds"))if(!references.contains(r.asText()))throw new IllegalArgumentException("Unknown reference");
  if(!status.equals("READY")){
   if(!result.path("files").isArray() || !result.path("files").isEmpty())throw new IllegalArgumentException("Blocked proposal must have no patch");
   return;
  }
  var verification=result.path("verification");
  if(verification.path("exitCode").asInt(-1)!=0 || verification.path("failed").asInt(-1)!=0 || verification.path("securityPassed").asInt()!=13 || verification.path("passed").asInt()<40 ||
     verification.path("suiteVersion").asInt()!=2 || verification.path("securityTotal").asInt()!=13 ||
     !"DOCKER_NETWORK_NONE".equals(verification.path("isolation").asText()))throw new IllegalArgumentException("Verification required");
  var checks=verification.path("securityChecks");Set<String> verified=new HashSet<>();
  if(!checks.isArray() || checks.size()!=SECURITY_TESTS.size())throw new IllegalArgumentException("Complete security checks required");
  for(var check:checks){
   if(!"PASSED".equals(check.path("status").asText()) || !verified.add(check.path("id").asText()))
    throw new IllegalArgumentException("Distinct passing security checks required");
  }
  if(!verified.equals(SECURITY_TESTS))throw new IllegalArgumentException("Unknown security checks");
  var files=result.path("files");if(!files.isArray() || files.size()!=1 || !TARGET.equals(files.get(0).path("path").asText()))throw new IllegalArgumentException("Edit scope");
  var file=files.get(0);String content=file.path("content").asText();
  if(content.length()<20 || content.getBytes(StandardCharsets.UTF_8).length>24000 || !file.path("beforeSha256").asText().matches("[a-f0-9]{64}") ||
    !file.path("beforeSha256").asText().equals(result.path("sourceHashes").path(TARGET).asText()))throw new IllegalArgumentException("Source identity");
  try{if(!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8))).equals(file.path("afterSha256").asText()))throw new IllegalArgumentException("Content digest");}
  catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
  boolean hasFinding=false,hasReference=false;
  for(var id:result.path("citedIds")){String key=id.asText();if(!findings.contains(key)&&!references.contains(key))throw new IllegalArgumentException("Invented citation");hasFinding|=findings.contains(key);hasReference|=references.contains(key);}
  if(!hasFinding||!hasReference)throw new IllegalArgumentException("Citations required");
 }
 @PostMapping("/internal/coding-proposals/{id}/result") @Transactional public Object complete(@PathVariable UUID id,@RequestBody JsonNode body){
  var job=db.one(SELECT+"WHERE c.id=? FOR UPDATE OF c",id);var result=body.path("result");String token=body.path("leaseToken").asText();
  // The retained token is a delivery receipt, not an active lease. Replays only acknowledge
  // the exact committed result and never overwrite a subsequent administrator decision.
  if(Set.of("READY","BLOCKED","APPROVED","REJECTED").contains(String.valueOf(job.get("status"))) &&
     !token.isBlank() && Objects.equals(token,job.get("leaseToken")) && result.equals(db.json.valueToTree(job.get("result"))))
   return Map.of("status",job.get("status"),"replayed",true);
  requireLease(id,token,job);UUID scan=UUID.fromString((String)job.get("scanId"));
  Set<String> findings=new HashSet<>(),references=new HashSet<>();
  for(var row:db.list("SELECT id,analysis FROM findings WHERE scan_id=? AND file_path=?",scan,TARGET)){
   findings.add((String)row.get("id"));for(var ref:db.json.valueToTree(row.get("analysis")).path("references"))references.add(ref.path("chunkId").asText());
  }
  try{
   validateResult(result,job,findings,references);
   if(job.get("architectureId")!=null){
    var image=db.one("SELECT image_sha256 FROM project_architectures WHERE id=?",UUID.fromString((String)job.get("architectureId")));
    if(!Objects.equals(image.get("imageSha256"),result.path("handoff").path("imageSha256").asText()))throw new IllegalArgumentException("Architecture digest mismatch");
   }
  }catch(IllegalArgumentException e){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,e.getMessage());}
  db.jdbc.update("UPDATE coding_proposals SET status=?,result=?::jsonb,finished_at=now(),lease_until=null WHERE id=?",result.path("status").asText(),result.toString(),id);
  db.log(scan,"CODING_FINISHED","coding-agent","INFO","Coding proposal "+result.path("status").asText());events.publish(scan.toString());return Map.of("status",result.path("status").asText());
 }
 public record Failure(String leaseToken,String errorCode){}
 @PostMapping("/internal/coding-proposals/{id}/failure") @Transactional public Object fail(@PathVariable UUID id,@RequestBody Failure failure){
  var job=leased(id,failure.leaseToken());String code=failure.errorCode();if(code==null||!code.matches("[A-Z_]{1,80}"))code="WORKER_FAILED";
  db.jdbc.update("UPDATE coding_proposals SET status='FAILED',error_code=?,finished_at=now(),lease_token=null,lease_until=null WHERE id=?",code,id);
  events.publish((String)job.get("scanId"));return Map.of("status","FAILED");
 }
 public record Decision(String decision){}
 @PostMapping("/api/coding-proposals/{id}/decision") @Transactional public Object decide(@PathVariable UUID id,@RequestBody Decision decision,Authentication auth){
  if(!Set.of("APPROVED","REJECTED").contains(String.valueOf(decision.decision())))throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
  var job=db.one(SELECT+"WHERE c.id=? FOR UPDATE OF c",id);
  if(!"READY".equals(job.get("status")))throw new ResponseStatusException(HttpStatus.CONFLICT,"검증을 통과한 검토 대기 수정안만 결정할 수 있습니다.");
  db.jdbc.update("UPDATE coding_proposals SET status=?,decided_by=?,decided_at=now() WHERE id=?",decision.decision(),auth.getName(),id);
  UUID scanId=UUID.fromString((String)job.get("scanId"));
  db.log(scanId,"CODING_DECIDED","backend","INFO",decision.decision());
  // A decided proposal is an informational notification, not another Agent approval.
  if("APPROVED".equals(decision.decision()))
   db.jdbc.update("INSERT INTO approvals(id,scan_id,action,proposal_id,status,decided_by,decided_at) VALUES(?,?,'CODING_PROPOSAL_APPROVED',?,'APPROVED',?,now()) ON CONFLICT(proposal_id,action) WHERE proposal_id IS NOT NULL DO NOTHING",UUID.randomUUID(),scanId,id,auth.getName());
  events.publish(scanId.toString());return Map.of("status",decision.decision());
 }
 @Scheduled(fixedDelay=30000) public void expire(){
  for(var row:db.list("UPDATE coding_proposals SET status='FAILED',error_code='WORKER_LEASE_EXPIRED',finished_at=now(),lease_token=null,lease_until=null WHERE status='RUNNING' AND lease_until<now() RETURNING scan_id"))events.publish((String)row.get("scanId"));
 }
}
