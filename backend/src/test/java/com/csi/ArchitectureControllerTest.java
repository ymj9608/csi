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
  byte[] png=new byte[]{(byte)0x89,'P','N','G',0x0d,0x0a};
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
}
