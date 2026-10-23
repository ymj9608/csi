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
}
