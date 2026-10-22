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
  assertDoesNotThrow(()->CodingProposals.validateProgress(new CodingProposals.Progress("token","GENERATING",2,120000)));
  for(var p:List.of(new CodingProposals.Progress("token","arbitrary source text",1,0),
      new CodingProposals.Progress("token","VERIFYING",3,0),new CodingProposals.Progress("token","VERIFYING",1,600001)))
   assertThrows(ResponseStatusException.class,()->CodingProposals.validateProgress(p));
 }
}
