package com.csi;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.*;
import java.util.UUID;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ProjectRegistrationTest {
 @TempDir Path temp;
 final JdbcTemplate jdbc=mock(JdbcTemplate.class);
 final Db db=new Db(jdbc,new ObjectMapper());
 MockMvc mvc;
 byte[] png;

 @BeforeEach void setup() throws Exception {
  Path policy=temp.resolve("policy.json"),catalog=temp.resolve("catalog.json");
  Files.writeString(policy,"{\"version\":\"test-v1\"}");Files.writeString(catalog,"[]");
  var api=new ApiController(db,mock(Events.class),new PolicyCatalog(db,policy.toString(),catalog.toString()),"test/project");
  mvc=MockMvcBuilders.standaloneSetup(api).build();
  var bytes=new ByteArrayOutputStream();
  ImageIO.write(new BufferedImage(2,2,BufferedImage.TYPE_INT_RGB),"png",bytes);png=bytes.toByteArray();
 }
 @Test void jsonWithoutImageIsRejected() throws Exception {
  mvc.perform(post("/api/projects").contentType("application/json")
   .content("{\"repository\":\"test/project\",\"defaultBranch\":\"main\"}"))
   .andExpect(status().isBadRequest());verifyNoInteractions(jdbc);
 }
 @Test void missingAndEmptyAttachmentsAreRejectedBeforeAnyInsert() throws Exception {
  mvc.perform(multipart("/api/projects").param("repository","test/project").param("defaultBranch","main"))
   .andExpect(status().isBadRequest());
  mvc.perform(multipart("/api/projects").file(new MockMultipartFile("architecture","empty.png","image/png",new byte[0]))
   .param("repository","test/project").param("defaultBranch","main")).andExpect(status().isBadRequest());
  verifyNoInteractions(jdbc);
 }
 @Test void invalidImageBytesAreRejectedBeforeAnyInsert() throws Exception {
  mvc.perform(multipart("/api/projects").file(new MockMultipartFile("architecture","fake.png","image/png",new byte[]{1,2,3}))
   .param("repository","test/project").param("defaultBranch","main")).andExpect(status().isBadRequest());
  verifyNoInteractions(jdbc);
 }
 @Test void oversizedImageIsRejectedBeforeAnyInsert() throws Exception {
  mvc.perform(multipart("/api/projects").file(new MockMultipartFile("architecture","large.png","image/png",new byte[5*1024*1024+1]))
   .param("repository","test/project").param("defaultBranch","main")).andExpect(status().isBadRequest());
  verifyNoInteractions(jdbc);
 }
 @Test void allowlistStillApplies() throws Exception {
  mvc.perform(multipart("/api/projects").file(new MockMultipartFile("architecture","image.png","image/png",png))
   .param("repository","other/project").param("defaultBranch","main")).andExpect(status().isBadRequest());
  verifyNoInteractions(jdbc);
 }
 @Test void validImageCreatesProjectPolicyAndQueuedDiagramForSameProject() throws Exception {
  var response=mvc.perform(multipart("/api/projects").file(new MockMultipartFile("architecture","image.png","image/png",png))
   .param("repository","test/project").param("defaultBranch","main"))
   .andExpect(status().isOk()).andExpect(jsonPath("$.architectureStatus").value("QUEUED"))
   .andReturn().getResponse();
  var result=db.json.readTree(response.getContentAsString());
  var id=UUID.fromString(result.get("id").asText());
  var diagramId=UUID.fromString(result.get("diagramId").asText());
  var ordered=inOrder(jdbc);
  ordered.verify(jdbc).update(contains("INSERT INTO projects("),eq(id),eq("test/project"),eq("main"));
  ordered.verify(jdbc).update(contains("INSERT INTO project_policies"),eq(id),eq("test-v1"),anyString());
  ordered.verify(jdbc).update(contains("INSERT INTO architecture_diagrams"),eq(diagramId),eq(id),eq(png),eq("image/png"));
 }
}
