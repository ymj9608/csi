package com.csi;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.web.server.ResponseStatusException;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ArchitectureContextsTest {
 final ObjectMapper json=new ObjectMapper();
 final JdbcTemplate jdbc=mock(JdbcTemplate.class);
 final Db db=spy(new Db(jdbc,json));
 final String model="ministral-3:8b-instruct-2512-q4_K_M",prompt="architecture-v1";
 final ArchitectureContexts service=new ArchitectureContexts(db,model,prompt);
 final UUID id=UUID.randomUUID(),project=UUID.randomUUID();
 final String token=UUID.randomUUID().toString();

 static MockMultipartFile image(String format) throws Exception {
  var output=new ByteArrayOutputStream();
  ImageIO.write(new BufferedImage(20,10,BufferedImage.TYPE_INT_RGB),format,output);
  return new MockMultipartFile("file","diagram."+format,"image/"+format,output.toByteArray());
 }
 Map<String,Object> job(String status,ObjectNode result){
  var job=new LinkedHashMap<String,Object>();
  job.put("id",id.toString());job.put("projectId",project.toString());job.put("status",status);job.put("leaseToken",token);
  job.put("imageSha256","a".repeat(64));job.put("model",model);job.put("promptVersion",prompt);job.put("sourceCommitSha","b".repeat(40));
  if(result!=null)job.put("result",json.convertValue(result,Map.class));
  doReturn(job).when(db).one(anyString(),eq(id));return job;
 }
 ObjectNode result(){
  var r=json.createObjectNode();
  r.put("schemaVersion",1).put("imageSha256","a".repeat(64)).put("model",model).put("promptVersion",prompt)
   .put("diagramType","ARCHITECTURE").put("summary","사용자, API 및 DB 간 데이터 흐름의 이미지 해석");
  var components=r.putArray("components");
  components.addObject().put("id","api").put("label","API").put("kind","service");
  components.addObject().put("id","db").put("label","DB").put("kind","storage");
  r.putArray("flows").addObject().put("from","api").put("to","db").put("data","회원 정보").put("protection","이미지에서 확인 불가");
  r.putArray("trustBoundaries");r.putArray("codeHints").add("backend/app/**/*.py");
  r.putArray("assumptions").add("이미지는 현재 실행 환경을 보증하지 않음");
  r.putArray("uncertainties").add("암호화 구현은 코드 검증 필요");
  r.putObject("metrics").put("wallDurationMs",1000).put("promptEvalCount",300);
  return r;
 }
 ObjectNode body(ObjectNode result){var body=json.createObjectNode();body.put("leaseToken",token);body.set("result",result);return body;}

 @Test void acceptsPngAndJpegAndDerivesDimensionsAndDigest() throws Exception {
  for(String format:List.of("png","jpeg")){
   var info=ArchitectureContexts.inspect(image(format));
   assertEquals(20,info.width());assertEquals(10,info.height());assertEquals("image/"+format,info.contentType());
   assertTrue(info.sha256().matches("[a-f0-9]{64}"));
  }
 }
 @Test void rejectsTypeSpoofingCorruptAndOversizedFiles() throws Exception {
  var png=image("png");
  var inputs=List.of(
   new MockMultipartFile("file","bad.png","image/png","<svg/>".getBytes()),
   new MockMultipartFile("file","bad.jpg","image/jpeg",png.getBytes()),
   new MockMultipartFile("file","bad.png","image/png",Arrays.copyOf(png.getBytes(),24)),
   new MockMultipartFile("file","huge.png","image/png",new byte[ArchitectureContexts.MAX_BYTES+1]));
  for(var input:inputs)assertEquals(400,assertThrows(ResponseStatusException.class,()->ArchitectureContexts.inspect(input)).getStatusCode().value());
  byte[] oversized=png.getBytes();
  java.nio.ByteBuffer.wrap(oversized).putInt(16,20000).putInt(20,20000);
  assertThrows(ResponseStatusException.class,()->ArchitectureContexts.inspect(new MockMultipartFile("file","huge.png","image/png",oversized)));
 }
 @Test void repeatedUploadUsesImmutableCacheAndProjectLock() throws Exception {
  var existing=job("READY",result());
  doReturn(Map.of("id",project.toString())).when(db).one(anyString(),eq(project));
  doReturn(List.of(existing)).when(db).list(anyString(),eq(project),anyString(),eq(model),eq(prompt),eq("b".repeat(40)));
  var response=(Map<?,?>)service.upload(project,image("png"),"b".repeat(40),new UsernamePasswordAuthenticationToken("reviewer",null));
  assertEquals(true,response.get("reused"));assertEquals(id.toString(),response.get("id"));assertFalse(response.containsKey("leaseToken"));
  verify(db).one("SELECT id FROM projects WHERE id=? FOR UPDATE",project);verifyNoInteractions(jdbc);
 }
 @Test void acceptsBoundaryButRejectsLongThinImagesBeyondWorkerEdgeLimit() throws Exception {
  for(int[] size:List.of(new int[]{8192,1},new int[]{1,8192},new int[]{8193,1},new int[]{1,8193},new int[]{16000,1})){
   var output=new ByteArrayOutputStream();
   ImageIO.write(new BufferedImage(size[0],size[1],BufferedImage.TYPE_INT_RGB),"png",output);
   var file=new MockMultipartFile("file","thin.png","image/png",output.toByteArray());
   if(size[0]<=8192 && size[1]<=8192){
    var info=ArchitectureContexts.inspect(file);assertEquals(size[0],info.width());assertEquals(size[1],info.height());
   } else {
    assertEquals(400,assertThrows(ResponseStatusException.class,()->ArchitectureContexts.inspect(file)).getStatusCode().value());
   }
  }
 }
 @Test void staleImageContextNeverClaimsSourceVerificationAndPendingNeverUsesPriorReady(){
  var ready=job("READY",result());
  var response=ArchitectureContexts.contextResponse(ready,"c".repeat(40));
  assertEquals(true,response.get("available"));assertEquals(false,response.get("sourceCommitMatches"));assertEquals("COMMIT_MISMATCH",response.get("staleness"));
  assertEquals(true,response.get("advisoryOnly"));assertEquals(true,response.get("codeVerificationRequired"));
  assertEquals("UNKNOWN",ArchitectureContexts.contextResponse(ready,"").get("staleness"));
  assertEquals(false,ArchitectureContexts.contextResponse(job("QUEUED",null),"b".repeat(40)).get("available"));
  assertEquals("NOT_PROVIDED",ArchitectureContexts.contextResponse(null,"").get("status"));
 }
 @Test void validatesIdentityGraphShapeAndSafeAdvisoryPaths(){
  var job=job("RUNNING",null);assertDoesNotThrow(()->ArchitectureContexts.validateResult(result(),job));
  for(String key:List.of("imageSha256","model","promptVersion")){
   var value=result();value.put(key,"wrong");assertThrows(IllegalArgumentException.class,()->ArchitectureContexts.validateResult(value,job));
  }
  var extra=result();extra.put("securityVerified",true);assertThrows(IllegalArgumentException.class,()->ArchitectureContexts.validateResult(extra,job));
  var flow=result();((ObjectNode)flow.path("flows").get(0)).put("from","invented");assertThrows(IllegalArgumentException.class,()->ArchitectureContexts.validateResult(flow,job));
  var duplicate=result();((ObjectNode)duplicate.path("components").get(1)).put("id","api");assertThrows(IllegalArgumentException.class,()->ArchitectureContexts.validateResult(duplicate,job));
  for(String path:List.of("../.env","/etc/passwd","C:\\private","https://example.com","backend/../../.env")){
   var unsafe=result();unsafe.putArray("codeHints").add(path);assertThrows(IllegalArgumentException.class,()->ArchitectureContexts.validateResult(unsafe,job));
  }
  var metrics=result();metrics.putObject("metrics").put("wallDurationMs",-1);assertThrows(IllegalArgumentException.class,()->ArchitectureContexts.validateResult(metrics,job));
 }
 @Test void exactResultReplayIsAcknowledgedWithoutWritingAndAlteredReplayRejected(){
  var result=result();job("READY",result);
  assertEquals(Map.of("status","READY","replayed",true),service.complete(id,body(result.deepCopy())));
  result.put("summary","changed");
  assertEquals(409,assertThrows(ResponseStatusException.class,()->service.complete(id,body(result))).getStatusCode().value());
  verifyNoInteractions(jdbc);
 }
 @Test void completionRequiresCurrentLeaseAndTerminatesExecutionLease(){
  job("RUNNING",null);doReturn(1L).when(db).count(anyString(),eq(id));var result=result();
  assertEquals(Map.of("status","READY","replayed",false),service.complete(id,body(result)));
  verify(jdbc).update(eq("UPDATE project_architectures SET status='READY',result=?::jsonb,finished_at=now(),lease_until=null WHERE id=?"),eq(result.toString()),eq(id));
 }
 @Test void wrongExpiredAndFailedLeasesRejectLateResults(){
  for(String status:List.of("FAILED","QUEUED","RUNNING")){
   job(status,null);doReturn(0L).when(db).count(anyString(),eq(id));
   assertEquals(409,assertThrows(ResponseStatusException.class,()->service.complete(id,body(result()))).getStatusCode().value());
  }
  doReturn(1L).when(db).count(anyString(),eq(id));var body=body(result());body.put("leaseToken","wrong");
  assertThrows(ResponseStatusException.class,()->service.complete(id,body));verifyNoInteractions(jdbc);
 }
 @Test void claimMustMatchConfiguredModelAndPrompt(){
  assertThrows(ResponseStatusException.class,()->service.claim(new ArchitectureContexts.Claim("wrong",prompt)));
  assertThrows(ResponseStatusException.class,()->service.claim(new ArchitectureContexts.Claim(model,"wrong")));
  verifyNoInteractions(jdbc);
 }
 @Test void onlyFailedJobCanRetry(){
  for(String status:List.of("READY","RUNNING","QUEUED")){
   doReturn(Map.of("status",status)).when(db).one(anyString(),eq(project),eq(id));
   assertThrows(ResponseStatusException.class,()->service.retry(project,id));
  }
  verifyNoInteractions(jdbc);
 }
 @Test void publicResponsesRemoveStorageAndWorkerCredentials(){
  var value=job("READY",result());value.put("imageBytes",new byte[]{1});value.put("leaseUntil","time");
  var response=ArchitectureContexts.publicJob(value);
  assertFalse(response.containsKey("imageBytes"));assertFalse(response.containsKey("leaseToken"));assertFalse(response.containsKey("leaseUntil"));
 }
 @Test void obsoleteQueuedJobsFailAndCannotBeRequeuedWithAnUnclaimableConfiguration(){
  service.expire();
  verify(jdbc).update(eq("UPDATE project_architectures SET status='FAILED',error_code='MODEL_OR_PROMPT_CHANGED',finished_at=now(),lease_token=null,lease_until=null WHERE status='QUEUED' AND (model<>? OR prompt_version<>?)"),eq(model),eq(prompt));
  clearInvocations(jdbc);
  for(var config:List.of(Map.of("model","old-model","promptVersion",prompt),Map.of("model",model,"promptVersion","old-prompt"))){
   var obsolete=new LinkedHashMap<String,Object>(config);obsolete.put("status","FAILED");
   doReturn(obsolete).when(db).one(anyString(),eq(project),eq(id));
   var error=assertThrows(ResponseStatusException.class,()->service.retry(project,id));
   assertEquals(409,error.getStatusCode().value());assertTrue(error.getReason().contains("다시 업로드"));
  }
  verifyNoInteractions(jdbc);
 }
}
