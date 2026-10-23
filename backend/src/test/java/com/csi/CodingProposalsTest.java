package com.csi;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.web.server.ResponseStatusException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class CodingProposalsTest {
 final ObjectMapper json=new ObjectMapper();
 final Map<String,Object> job=Map.of("repository","ymj9608/Lichu","commitSha","a".repeat(40));
 ObjectNode result() throws Exception {
  var r=json.createObjectNode();
  r.put("schemaVersion",1).put("engineVersion","3").put("profile","lichu-signup-v1").put("repository","ymj9608/Lichu")
   .put("commitSha","a".repeat(40)).put("model",CodingProposals.MODEL).put("status","READY");
  r.putArray("findingIds").add("finding");r.putArray("referenceIds").add("reference");
  r.putArray("citedIds").add("finding").add("reference");
  var verification=r.putObject("verification").put("exitCode",0).put("failed",0).put("securityPassed",13).put("passed",40)
   .put("suiteVersion",2).put("securityTotal",13).put("isolation","DOCKER_NETWORK_NONE");
  var checks=verification.putArray("securityChecks");
  CodingProposals.SECURITY_TESTS.forEach(id->checks.addObject().put("id",id).put("status","PASSED"));
  String source="def lab_version():\n    return 'after-fix'\n";
  r.putObject("sourceHashes").put(CodingProposals.TARGET,"b".repeat(64));
  r.putArray("files").addObject().put("path",CodingProposals.TARGET).put("content",source)
   .put("beforeSha256","b".repeat(64)).put("afterSha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(source.getBytes(StandardCharsets.UTF_8))));
  return r;
 }
 void validate(ObjectNode r){CodingProposals.validateResult(r,job,Set.of("finding"),Set.of("reference"));}
 @Test void acceptsVerifiedProposal() throws Exception {assertDoesNotThrow(()->validate(result()));}
 @Test void rejectsStaleIdentityTamperingScopeAndInventedCitations() throws Exception {
  var r=result();r.put("commitSha","c".repeat(40));assertThrows(IllegalArgumentException.class,()->validate(r));
  var modified=result();((ObjectNode)modified.path("files").get(0)).put("content","changed candidate after validation");assertThrows(IllegalArgumentException.class,()->validate(modified));
  var scope=result();((ObjectNode)scope.path("files").get(0)).put("path","backend/tests/test.py");assertThrows(IllegalArgumentException.class,()->validate(scope));
  var cited=result();cited.putArray("citedIds").add("made-up-law");assertThrows(IllegalArgumentException.class,()->validate(cited));
  var hashes=result();hashes.putObject("sourceHashes");assertThrows(IllegalArgumentException.class,()->validate(hashes));
 }
 @Test void requiresAllTestsAndIsolation() throws Exception {
  for(var key:List.of("exitCode","failed","securityPassed","passed","suiteVersion","securityTotal")){
   var r=result();((ObjectNode)r.path("verification")).put(key,-1);assertThrows(IllegalArgumentException.class,()->validate(r));
  }
  var r=result();((ObjectNode)r.path("verification")).put("isolation","HOST");assertThrows(IllegalArgumentException.class,()->validate(r));
 }
 @Test void requiresIdentifiableCompleteSecurityChecks() throws Exception {
  var missing=result();((ObjectNode)missing.path("verification")).remove("securityChecks");assertThrows(IllegalArgumentException.class,()->validate(missing));
  var duplicate=result();var checks=(com.fasterxml.jackson.databind.node.ArrayNode)duplicate.path("verification").path("securityChecks");checks.set(0,checks.get(1));assertThrows(IllegalArgumentException.class,()->validate(duplicate));
  var invented=result();((ObjectNode)invented.path("verification").path("securityChecks").get(0)).put("id","invented");assertThrows(IllegalArgumentException.class,()->validate(invented));
  for(String status:List.of("FAILED","SKIPPED")){
   var failed=result();((ObjectNode)failed.path("verification").path("securityChecks").get(0)).put("status",status);assertThrows(IllegalArgumentException.class,()->validate(failed));
  }
  var old=result();old.put("engineVersion","2");assertThrows(IllegalArgumentException.class,()->validate(old));
 }
 @Test void blockedResultCannotContainApplicablePatch() throws Exception {
  var r=result();r.put("status","BLOCKED");assertThrows(IllegalArgumentException.class,()->validate(r));
  r.putArray("files");assertDoesNotThrow(()->validate(r));
 }
 @Test void onlyReadyProposalCanBeApproved(){
  Db db=mock(Db.class);Events events=mock(Events.class);var service=new CodingProposals(db,events,true,"ymj9608/Lichu");
  UUID id=UUID.randomUUID();
  for(String state:List.of("QUEUED","RUNNING","BLOCKED","FAILED","APPROVED","REJECTED")){
   when(db.one(anyString(),eq(id))).thenReturn(Map.of("status",state));
   var error=assertThrows(ResponseStatusException.class,()->service.decide(id,new CodingProposals.Decision("APPROVED"),new UsernamePasswordAuthenticationToken("reviewer",null)));
   assertEquals(409,error.getStatusCode().value());
  }
  verifyNoInteractions(events);
 }
 @Test void expiredOrWrongLeaseCannotUpload(){
  Db db=mock(Db.class);var service=new CodingProposals(db,mock(Events.class),true,"ymj9608/Lichu");UUID id=UUID.randomUUID();
  when(db.one(anyString(),eq(id))).thenReturn(Map.of("status","RUNNING","leaseToken","valid"));
  assertThrows(ResponseStatusException.class,()->service.leased(id,"wrong"));
  when(db.count(anyString(),eq(id))).thenReturn(0L);
  assertThrows(ResponseStatusException.class,()->service.leased(id,"valid"));
 }
 @Test void progressOnlyAcceptsBoundedKnownStages(){
  assertDoesNotThrow(()->CodingProposals.validateProgress(new CodingProposals.Progress("token","ARCHITECTURE_CONTEXT",0,0,"저장된 분석 결과 참고")));
  assertThrows(ResponseStatusException.class,()->CodingProposals.validateProgress(new CodingProposals.Progress("token","ARCHITECTURE_CONTEXT",0,0,"x".repeat(201))));
  assertDoesNotThrow(()->CodingProposals.validateProgress(new CodingProposals.Progress("token","GENERATING",2,120000)));
  for(var p:List.of(new CodingProposals.Progress("token","arbitrary source text",1,0),
      new CodingProposals.Progress("token","VERIFYING",3,0),new CodingProposals.Progress("token","VERIFYING",1,900001)))
   assertThrows(ResponseStatusException.class,()->CodingProposals.validateProgress(p));
 }

 @Test void orchestrationIsRequiredForPinnedImageButNotHistoricalJobs() throws Exception {
  var pinned=new HashMap<String,Object>(job);pinned.put("architectureId","image-id");
  var r=result();
  assertThrows(IllegalArgumentException.class,()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  r.put("engineVersion","4");
  var handoff=r.putObject("handoff").put("mode","vlm-orchestrator-v1").put("provider","openai").put("model","gpt-6.1-sol").put("architectureId","image-id")
   .put("commitSha","a".repeat(40)).put("status","READY").put("conclusion","실행 검증 결과를 확인한 관리자 검토용 수정안")
   .put("imageSha256","a".repeat(64)).put("instruction","근거 finding reference에 따른 수정 지시문");
  handoff.putObject("metrics").put("inputTokens",500).put("outputTokens",200).put("wallDurationMs",5000);
  var trace=handoff.putArray("trace");
  for(String tool:List.of("delegate_coding","run_verification","finish_review"))trace.addObject().put("tool",tool).put("status","OK");
  assertDoesNotThrow(()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  handoff.put("model","qwen3-vl:8b");
  assertThrows(IllegalArgumentException.class,()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  handoff.put("provider","ollama");
  assertDoesNotThrow(()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  handoff.put("provider","openai").put("model","gpt-6.1-sol");
  trace.remove(1);
  assertThrows(IllegalArgumentException.class,()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  handoff.put("status","BLOCKED");r.put("status","BLOCKED");r.putArray("files");handoff.put("instruction","");trace.removeAll();
  assertDoesNotThrow(()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  ((ObjectNode)r.path("handoff")).put("architectureId","other-image");
  assertThrows(IllegalArgumentException.class,()->CodingProposals.validateResult(r,pinned,Set.of("finding"),Set.of("reference")));
  assertDoesNotThrow(()->CodingProposals.validateProgress(new CodingProposals.Progress("token","VLM_PLANNING",0,150000)));
 }
 @Test void staleImageDoesNotQueueNewProposal(){
  Db db=mock(Db.class);var service=new CodingProposals(db,mock(Events.class),true,"ymj9608/Lichu");
  UUID id=UUID.randomUUID(),project=UUID.randomUUID();
  when(db.one(anyString(),eq(id))).thenReturn(Map.of("projectId",project.toString(),"repository","ymj9608/Lichu","status","COMPLETED","commitSha","a".repeat(40)));
  when(db.count(anyString(),eq(id),eq(CodingProposals.TARGET))).thenReturn(1L);
  when(db.list(anyString(),eq(id))).thenReturn(List.of());
  when(db.list(anyString(),eq(project))).thenReturn(List.of(Map.of("id",UUID.randomUUID().toString(),"sourceCommitSha","b".repeat(40))));
  assertEquals(409,assertThrows(ResponseStatusException.class,()->service.queue(id,true)).getStatusCode().value());
 }
 @Test void missingImageQueuesCodeOnlyProposal(){
  var jdbc=mock(org.springframework.jdbc.core.JdbcTemplate.class);
  Db db=spy(new Db(jdbc,json));var service=new CodingProposals(db,mock(Events.class),true,"ymj9608/Lichu");
  UUID id=UUID.randomUUID(),project=UUID.randomUUID();
  doReturn(Map.of("projectId",project.toString(),"repository","ymj9608/Lichu","status","COMPLETED","commitSha","a".repeat(40))).when(db).one(anyString(),eq(id));
  doReturn(Map.of("status","QUEUED")).when(db).one(startsWith(CodingProposals.SELECT),any(UUID.class));
  doReturn(1L).when(db).count(anyString(),eq(id),eq(CodingProposals.TARGET));
  doReturn(List.of()).when(db).list(anyString(),any(UUID.class));
  assertEquals("QUEUED",service.queue(id,true).get("status"));
  verify(jdbc).update(startsWith("INSERT INTO coding_proposals"),any(UUID.class),eq(id),isNull());
 }
}
