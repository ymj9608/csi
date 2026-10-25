package com.csi;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ArchitectureControllerTest {
 final JdbcTemplate jdbc=mock(JdbcTemplate.class);
 final Db db=spy(new Db(jdbc,new ObjectMapper()));
 final ArchitectureController controller=new ArchitectureController(db);
 final UUID projectId=UUID.randomUUID();

 @Test void postArchitecture_storesQueuedDiagram() throws Exception {
  doReturn(Map.of("id",projectId.toString())).when(db).one(anyString(),eq(projectId));
  byte[] png=ArchitectureContextsTest.image("png").getBytes();
  var file=new MockMultipartFile("file","diagram.png","image/png",png);
  var response=controller.upload(projectId,file);
  assertEquals(201,response.getStatusCode().value());
  var body=(Map<?,?>)response.getBody();
  assertEquals("QUEUED",body.get("status"));
  assertNotNull(body.get("id"));
  verify(jdbc).update(contains("INSERT INTO architecture_diagrams"),any(UUID.class),eq(projectId),eq(png),eq("image/png"));
 }

 @Test void postArchitecture_returns404ForNonexistentProject() throws Exception {
  doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND)).when(db).one(anyString(),eq(projectId));
  var file=new MockMultipartFile("file","diagram.png","image/png",new byte[]{1,2,3});
  var error=assertThrows(ResponseStatusException.class,()->controller.upload(projectId,file));
  assertEquals(404,error.getStatusCode().value());
  verifyNoInteractions(jdbc);
 }

 @Test void getArchitecture_returns404WhenNone(){
  doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND)).when(db).one(anyString(),eq(projectId));
  var error=assertThrows(ResponseStatusException.class,()->controller.get(projectId));
  assertEquals(404,error.getStatusCode().value());
 }

 @Test void claim_transitionsQueuedToLoadingModel(){
  UUID diagramId=UUID.randomUUID();
  doReturn(List.of(Map.of("id",diagramId.toString()))).when(db).list(contains("FOR UPDATE SKIP LOCKED"),eq(projectId));
  var response=controller.claim(projectId);
  assertEquals(200,response.getStatusCode().value());
  assertEquals(diagramId,((Map<?,?>)response.getBody()).get("diagramId"));
  verify(jdbc).update(contains("SET status='LOADING_MODEL'"),eq(diagramId));
 }

 @Test void claim_returns204WhenNoneQueued(){
  doReturn(List.of()).when(db).list(contains("FOR UPDATE SKIP LOCKED"),eq(projectId));
  var response=controller.claim(projectId);
  assertEquals(204,response.getStatusCode().value());
  verifyNoInteractions(jdbc);
 }

 @Test void progress_transitionsLoadingModelToAnalyzing(){
  UUID diagramId=UUID.randomUUID();
  when(jdbc.update(contains("SET status='ANALYZING'"),eq(diagramId))).thenReturn(1);
  var result=controller.progress(diagramId,new ArchitectureController.Progress("ANALYZING"));
  assertEquals("ANALYZING",((Map<?,?>)result).get("status"));
 }

 @Test void progress_rejects409FromWrongState(){
  UUID diagramId=UUID.randomUUID();
  when(jdbc.update(contains("SET status='ANALYZING'"),eq(diagramId))).thenReturn(0);
  var error=assertThrows(ResponseStatusException.class,()->controller.progress(diagramId,new ArchitectureController.Progress("ANALYZING")));
  assertEquals(409,error.getStatusCode().value());
 }

 @Test void postResult_setsExtractedAndStoresComponentsAndSummary(){
  UUID diagramId=UUID.randomUUID();
  var components=List.of(new ArchitectureController.Component("Isolated CSI Lab Mode","격리된 연습 환경","ISOLATED","OBSERVED"));
  when(jdbc.update(contains("SET status='EXTRACTED'"),anyString(),anyString(),eq(diagramId))).thenReturn(1);
  var result=controller.result(diagramId,new ArchitectureController.Result(components,"Lichu는 라이선스 관리 서비스와 격리된 연습 환경으로 구성됩니다."));
  assertEquals("EXTRACTED",((Map<?,?>)result).get("status"));
  verify(jdbc).update(contains("SET status='EXTRACTED'"),anyString(),eq("Lichu는 라이선스 관리 서비스와 격리된 연습 환경으로 구성됩니다."),eq(diagramId));
 }

 @Test void postResult_rejects400OnMissingFields(){
  UUID diagramId=UUID.randomUUID();
  var error=assertThrows(ResponseStatusException.class,()->controller.result(diagramId,new ArchitectureController.Result(List.of(),"summary")));
  assertEquals(400,error.getStatusCode().value());
  verifyNoInteractions(jdbc);
 }

 @Test void uploadRejectsDisguisedOrOversizedImagesWithoutReplacingExistingResult() throws Exception {
  doReturn(Map.of("id",projectId.toString())).when(db).one(anyString(),eq(projectId));
  for(var file:List.of(new MockMultipartFile("file","x.png","image/png","not an image".getBytes()),
      new MockMultipartFile("file","large.png","image/png",new byte[5*1024*1024+1]))){
   assertThrows(ResponseStatusException.class,()->controller.upload(projectId,file));
  }
  verifyNoInteractions(jdbc);
 }

 @Test void invalidModelOutputIsAClientErrorWithoutSavingPartialData(){
  var valid=new ArchitectureController.Component("API","service","UNKNOWN","OBSERVED");
  var invalid=List.of(new ArchitectureController.Result(List.of(valid),"x".repeat(181)),
    new ArchitectureController.Result(Collections.nCopies(7,valid),"summary"),
    new ArchitectureController.Result(Arrays.asList((ArchitectureController.Component)null),"summary"),
    new ArchitectureController.Result(List.of(new ArchitectureController.Component("API","role",null,"OBSERVED")),"summary"),
    new ArchitectureController.Result(List.of(new ArchitectureController.Component("API","role","UNKNOWN",null)),"summary"));
  for(var r:invalid)assertEquals(400,assertThrows(ResponseStatusException.class,()->controller.result(UUID.randomUUID(),r)).getStatusCode().value());
  verifyNoInteractions(jdbc);
 }

 @Test void failure_doesNotPublishRawErrorOrOverwriteSuccess(){
  UUID diagram=UUID.randomUUID();
  var invalid=assertThrows(ResponseStatusException.class,()->controller.failure(diagram,new ArchitectureController.Failure("token=private")));
  assertEquals(400,invalid.getStatusCode().value());
  verifyNoInteractions(jdbc);
  doReturn(Map.of("status","EXTRACTED")).when(db).one(anyString(),eq(diagram));
  var conflict=assertThrows(ResponseStatusException.class,()->controller.failure(diagram,new ArchitectureController.Failure("MODEL_TIMEOUT")));
  assertEquals(409,conflict.getStatusCode().value());
  verify(jdbc).update(contains("status IN ('LOADING_MODEL','ANALYZING')"),eq("MODEL_TIMEOUT"),eq(diagram));
 }

 @Test void failure_isRecordedAndDuplicateDeliveryIsAccepted(){
  UUID diagram=UUID.randomUUID();
  when(jdbc.update(contains("SET status='FAILED'"),eq("INVALID_RESULT"),eq(diagram))).thenReturn(1,0);
  doReturn(Map.of("status","FAILED")).when(db).one(anyString(),eq(diagram));
  assertEquals(Map.of("status","FAILED"),controller.failure(diagram,new ArchitectureController.Failure("INVALID_RESULT")));
  assertEquals(Map.of("status","FAILED"),controller.failure(diagram,new ArchitectureController.Failure("INVALID_RESULT")));
 }

 @Test void expiredOrReplacedJobCannotPublishLateSuccess(){
  var result=new ArchitectureController.Result(List.of(new ArchitectureController.Component("API","service","UNKNOWN","OBSERVED")),"summary");
  var error=assertThrows(ResponseStatusException.class,()->controller.result(UUID.randomUUID(),result));
  assertEquals(409,error.getStatusCode().value());
  verify(jdbc).update(contains("AND status='ANALYZING'"),anyString(),eq("summary"),any(UUID.class));
 }

 @Test void retryChangesJobIdAndOnlyAcceptsCurrentFailedJob(){
  UUID old=UUID.randomUUID();
  when(jdbc.update(contains("AND status='FAILED'"),any(UUID.class),eq(projectId),eq(old))).thenReturn(1,0);
  var result=(Map<?,?>)controller.retry(projectId,new ArchitectureController.Retry(old));
  assertEquals("QUEUED",result.get("status"));
  assertNotEquals(old,result.get("id"));
  assertEquals(409,assertThrows(ResponseStatusException.class,()->controller.retry(projectId,new ArchitectureController.Retry(old))).getStatusCode().value());
 }

 @Test void timeoutCoversOnlyActiveJobsAndAlsoRunsDuringStatusRead(){
  controller.expire();
  verify(jdbc).update(contains("status IN ('LOADING_MODEL','ANALYZING') AND updated_at <"),eq(2100));
  doReturn(Map.of("status","FAILED","errorCode","WORKER_TIMEOUT")).when(db).one(anyString(),eq(projectId));
  assertEquals("FAILED",((Map<?,?>)controller.get(projectId)).get("status"));
  verify(jdbc).update(contains("project_id=? AND status IN ('LOADING_MODEL','ANALYZING')"),eq(projectId),eq(2100));
 }
}
