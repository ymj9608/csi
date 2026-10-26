package com.csi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.util.UUID;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers=ArchitectureController.class,properties="csi.internal-token=architecture-test-token-32-characters-long")
@Import(Security.class)
class ArchitectureDiagramSecurityTest {
 @Autowired MockMvc mvc;
 @MockitoBean Db db;
 @MockitoBean org.springframework.scheduling.TaskScheduler scheduler;
 final String id=UUID.randomUUID().toString();
 final String retry="/api/projects/"+id+"/architecture/retry";
 final String body="{\"diagramId\":\""+UUID.randomUUID()+"\"}";

 @Test void retryRequiresReviewerAndCsrf() throws Exception {
  mvc.perform(post(retry).with(csrf()).contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isUnauthorized());
  mvc.perform(post(retry).with(user("member").roles("MEMBER")).with(csrf()).contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isForbidden());
  mvc.perform(post(retry).with(user("reviewer").roles("SECURITY_REVIEWER")).contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isForbidden());
  verifyNoInteractions(db);
 }
 @Test void reviewerCannotReportWorkerFailure() throws Exception {
  mvc.perform(post("/internal/architecture/"+id+"/failure").with(user("reviewer").roles("SECURITY_REVIEWER")).with(csrf())
    .contentType(MediaType.APPLICATION_JSON).content("{\"errorCode\":\"WORKER_ERROR\"}")).andExpect(status().isUnauthorized());
  verifyNoInteractions(db);
 }
 @Test void internalBearerDoesNotAuthorizeReviewerRetry() throws Exception {
  mvc.perform(post(retry).header("Authorization","Bearer architecture-test-token-32-characters-long").with(csrf())
    .contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isUnauthorized());
  verifyNoInteractions(db);
 }
}
