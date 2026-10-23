package com.csi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.util.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers=ArchitectureContexts.class,properties="csi.internal-token=architecture-test-token-32-characters-long")
@Import(Security.class)
class ArchitectureContextsSecurityTest {
 @Autowired MockMvc mvc;
 @MockitoBean Db db;
 @MockitoBean org.springframework.scheduling.TaskScheduler scheduler;
 final String project=UUID.randomUUID().toString();
 final String list="/api/projects/"+project+"/architectures";
 final String claim="/internal/architectures/claim";
 final String body="{\"model\":\"ministral-3:8b-instruct-2512-q4_K_M\",\"promptVersion\":\"architecture-v1\"}";

 @Test void publicArchitectureRequiresReviewerSession() throws Exception {
  mvc.perform(get(list)).andExpect(status().isUnauthorized());
  mvc.perform(get(list).with(user("member").roles("MEMBER"))).andExpect(status().isForbidden());
  mvc.perform(get(list).with(user("reviewer").roles("SECURITY_REVIEWER"))).andExpect(status().isOk()).andExpect(jsonPath("$.advisoryOnly").value(true));
 }
 @Test void reviewerUploadNeedsCsrf() throws Exception {
  mvc.perform(multipart(list).file(ArchitectureContextsTest.image("png")).with(user("reviewer").roles("SECURITY_REVIEWER")))
   .andExpect(status().isForbidden());
  verifyNoInteractions(db);
 }
 @Test void reviewerCannotClaimWorkerJobsWithoutInternalBearer() throws Exception {
  mvc.perform(post(claim).contentType(MediaType.APPLICATION_JSON).content(body).with(user("reviewer").roles("SECURITY_REVIEWER")).with(csrf()))
   .andExpect(status().isUnauthorized());
  mvc.perform(post(claim).header("Authorization","Bearer incorrect").contentType(MediaType.APPLICATION_JSON).content(body))
   .andExpect(status().isUnauthorized());
  verifyNoInteractions(db);
 }
 @Test void internalBearerCanClaimWithoutCsrf() throws Exception {
  when(db.list(anyString(),anyString(),anyString())).thenReturn(List.of());
  mvc.perform(post(claim).header("Authorization","Bearer architecture-test-token-32-characters-long").contentType(MediaType.APPLICATION_JSON).content(body))
   .andExpect(status().isOk()).andExpect(jsonPath("$.available").value(false));
 }
 @Test void internalBearerCannotReadReviewerApi() throws Exception {
  mvc.perform(get(list).header("Authorization","Bearer architecture-test-token-32-characters-long"))
   .andExpect(status().isUnauthorized());
 }

 @Test void selectionRequiresCsrfAndProjectOwnedImage() throws Exception {
  String image=UUID.randomUUID().toString();String select=list+"/"+image+"/select-for-coding";
  mvc.perform(post(select).with(user("reviewer").roles("SECURITY_REVIEWER"))).andExpect(status().isForbidden());
  mvc.perform(post(select).with(user("member").roles("MEMBER")).with(csrf())).andExpect(status().isForbidden());
  verifyNoInteractions(db);
  when(db.one(contains("project_architectures"),eq(UUID.fromString(project)),eq(UUID.fromString(image))))
   .thenThrow(new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.NOT_FOUND));
  mvc.perform(post(select).with(user("reviewer").roles("SECURITY_REVIEWER")).with(csrf())).andExpect(status().isNotFound());
 }
}
