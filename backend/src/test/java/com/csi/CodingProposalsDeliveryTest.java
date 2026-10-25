package com.csi;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class CodingProposalsDeliveryTest {
 final ObjectMapper json=new ObjectMapper();
 final JdbcTemplate jdbc=mock(JdbcTemplate.class);
 final Db db=spy(new Db(jdbc,json));
 final Events events=mock(Events.class);
 final CodingProposals service=new CodingProposals(db,events,true,"ymj9608/Lichu");
 final UUID id=UUID.randomUUID(),scan=UUID.randomUUID();
 final String token=UUID.randomUUID().toString();

 Map<String,Object> job(String status,ObjectNode result){
  var job=new LinkedHashMap<String,Object>();
  job.put("status",status);job.put("leaseToken",token);job.put("scanId",scan.toString());
  job.put("repository","ymj9608/Lichu");job.put("commitSha","a".repeat(40));
  if(result!=null)job.put("result",json.convertValue(result,Map.class));
  doReturn(job).when(db).one(anyString(),eq(id));
  return job;
 }
 ObjectNode result() throws Exception {return new CodingProposalsTest().result();}
 ObjectNode body(ObjectNode result){var body=json.createObjectNode();body.put("leaseToken",token);body.set("result",result);return body;}

 @Test void initialCommitRetainsReceiptButEndsExecutionLease() throws Exception {
  var result=result();job("RUNNING",null);
  doReturn(1L).when(db).count(anyString(),eq(id));
  doReturn(List.of(Map.of("id","finding","analysis",Map.of("references",List.of(Map.of("chunkId","reference"))))))
   .when(db).list(anyString(),eq(scan),eq(CodingProposals.TARGET));
  assertEquals(Map.of("status","READY"),service.complete(id,body(result)));
  verify(jdbc).update(eq("UPDATE coding_proposals SET status=?,result=?::jsonb,finished_at=now(),lease_until=null WHERE id=?"),eq("READY"),eq(result.toString()),eq(id));
  verify(events).publish(scan.toString());
 }
 @Test void identicalResultReplayNeverOverwritesAdministratorDecision() throws Exception {
  var result=result();
  for(String status:List.of("READY","BLOCKED","APPROVED","REJECTED")){
   job(status,result);
   assertEquals(Map.of("status",status,"replayed",true),service.complete(id,body(result.deepCopy())));
  }
  verifyNoInteractions(jdbc,events);
 }
 @Test void wrongReceiptAndChangedResultAreRejected() throws Exception {
  var result=result();job("APPROVED",result);
  var wrong=body(result);wrong.put("leaseToken",UUID.randomUUID().toString());
  assertEquals(409,assertThrows(ResponseStatusException.class,()->service.complete(id,wrong)).getStatusCode().value());
  var altered=result.deepCopy();altered.put("reason","replace previously approved proposal");
  assertEquals(409,assertThrows(ResponseStatusException.class,()->service.complete(id,body(altered))).getStatusCode().value());
  verifyNoInteractions(jdbc,events);
 }
 @Test void expiredRunningAndFailedJobsCannotAcceptLateResult() throws Exception {
  var result=result();
  for(String status:List.of("RUNNING","FAILED","QUEUED")){
   job(status,result);doReturn(0L).when(db).count(anyString(),eq(id));
   assertEquals(409,assertThrows(ResponseStatusException.class,()->service.complete(id,body(result))).getStatusCode().value());
  }
  verifyNoInteractions(jdbc,events);
 }
 @Test void oldPersistedResultsCanBeAcknowledgedWithoutRevalidatingAsNewSuite() throws Exception {
  var old=result();old.put("engineVersion","2");((ObjectNode)old.path("verification")).put("securityPassed",7).put("passed",34);
  job("APPROVED",old);
  assertEquals(Map.of("status","APPROVED","replayed",true),service.complete(id,body(old)));
  verifyNoInteractions(jdbc,events);
 }
 @Test void publicResponsesNeverExposeReceiptOrExecutionLease(){
  var job=new LinkedHashMap<String,Object>();job.put("status","READY");job.put("leaseToken",token);job.put("leaseUntil","time");
  assertEquals(Map.of("status","READY"),CodingProposals.publicJob(job));
  assertEquals(token,job.get("leaseToken"));
 }
}
