package com.csi;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ApprovalNotificationsTest {
 final JdbcTemplate jdbc=mock(JdbcTemplate.class);
 final Db db=spy(new Db(jdbc,new ObjectMapper()));
 final Events events=mock(Events.class);
 final ApiController api=new ApiController(db,events,mock(PolicyCatalog.class),"example/project");
 final UUID scan=UUID.randomUUID(),id=UUID.randomUUID(),project=UUID.randomUUID();
 final UsernamePasswordAuthenticationToken auth=new UsernamePasswordAuthenticationToken("reviewer",null);

 @Test void approvedProposalCreatesIndependentDecidedNotification(){
  var coding=new CodingProposals(db,events,true,"example/project");
  doReturn(Map.of("status","READY","scanId",scan.toString())).when(db).one(anyString(),eq(id));
  coding.decide(id,new CodingProposals.Decision("APPROVED"),auth);
  verify(jdbc).update(contains("ON CONFLICT(proposal_id,action) WHERE proposal_id IS NOT NULL"),any(UUID.class),eq(scan),eq(id),eq("reviewer"));
  verify(jdbc,never()).update(startsWith("UPDATE agent_checkpoints"),any(Object[].class));
 }
 @Test void rejectedProposalDoesNotCreateNotification(){
  var coding=new CodingProposals(db,events,true,"example/project");
  doReturn(Map.of("status","READY","scanId",scan.toString())).when(db).one(anyString(),eq(id));
  coding.decide(id,new CodingProposals.Decision("REJECTED"),auth);
  verify(jdbc,never()).update(startsWith("INSERT INTO approvals"),any(Object[].class));
 }
 @Test void notificationCannotResumeAgentOrAuthorizeSecurityIssue(){
  doReturn(Map.of("action","CODING_PROPOSAL_APPROVED","status","APPROVED","scanId",scan.toString())).when(db).one(anyString(),eq(id));
  assertEquals(409,assertThrows(ResponseStatusException.class,()->api.decision(id,new ApiController.Decision("APPROVED"),auth)).getStatusCode().value());
  assertEquals(403,assertThrows(ResponseStatusException.class,()->api.issue(id)).getStatusCode().value());
  verifyNoInteractions(jdbc,events);
 }
 @Test void scanResumeLookupSelectsOnlySecurityReview(){
  doReturn(Map.of("action","CREATE_SECURITY_REVIEW_ISSUE")).when(db).one(anyString(),eq(scan));
  api.scanApproval(scan);
  verify(db).one(contains("a.action='CREATE_SECURITY_REVIEW_ISSUE'"),eq(scan));
 }
 @Test void securityReviewDecisionStillEnqueuesCheckpointResume(){
  doReturn(Map.of("action","CREATE_SECURITY_REVIEW_ISSUE","status","PENDING","scanId",scan.toString())).when(db).one(anyString(),eq(id));
  doReturn(Map.of("projectId",project.toString(),"repository","example/project","commitSha","a".repeat(40))).when(db).one(anyString(),eq(scan));
  assertEquals(Map.of("status","APPROVED"),api.decision(id,new ApiController.Decision("APPROVED"),auth));
  verify(jdbc).update(startsWith("UPDATE agent_checkpoints"),eq(scan));
  verify(jdbc).update(startsWith("INSERT INTO event_outbox"),any(UUID.class),eq(scan),eq("scan.request"),contains("APPROVAL_DECIDED"));
 }
 @Test void extractionLookupIsProjectScopedAndMatchesPinnedImage(){
  var coding=new CodingProposals(db,events,true,"example/project");
  var diagram=Map.<String,Object>of("id",id.toString(),"status","EXTRACTED");
  doReturn(List.of(diagram)).when(db).list(anyString(),eq(project));
  assertEquals(diagram,coding.architectureDiagram(Map.of("projectId",project.toString())));
  verify(db).list(contains("d.project_id=? AND d.status='EXTRACTED'"),eq(project));
  doReturn(List.of()).when(db).list(anyString(),eq(project),eq(id));
  assertTrue(coding.architectureDiagram(Map.of("projectId",project.toString(),"architectureId",id.toString())).isEmpty());
  verify(db).list(contains("a.image_bytes=d.image"),eq(project),eq(id));
 }
 @Test void progressRetainsArchitectureNoteWithoutDelay(){
  var coding=spy(new CodingProposals(db,events,true,"example/project"));
  doReturn(Map.of("scanId",scan.toString())).when(coding).leased(id,"lease");
  coding.progress(id,new CodingProposals.Progress("lease","ARCHITECTURE_CONTEXT",0,0,"관련 후보"));
  verify(jdbc).update(contains("coalesce(progress"),contains("architectureNote"),eq(id));
 }
}
