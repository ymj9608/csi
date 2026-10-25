package com.csi;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

/** Optional real PostgreSQL test. Creates/drops only its randomly named isolated schema. */
@EnabledIfEnvironmentVariable(named="CSI_ARCHITECTURE_TEST_DATABASE_URL",matches=".+")
class ArchitectureContextsPostgresIT {
 static JdbcTemplate admin;
 static Db db;
 static String schema;
 static ArchitectureContexts service;
 static TransactionTemplate tx;
 static final String MODEL="ministral-3:8b-instruct-2512-q4_K_M",PROMPT="architecture-v1";

 @BeforeAll static void database(){
  String url=System.getenv("CSI_ARCHITECTURE_TEST_DATABASE_URL");
  String user=System.getenv().getOrDefault("CSI_ARCHITECTURE_TEST_DATABASE_USER","csi");
  String password=System.getenv().getOrDefault("CSI_ARCHITECTURE_TEST_DATABASE_PASSWORD","");
  admin=new JdbcTemplate(new DriverManagerDataSource(url,user,password));
  schema="architecture_it_"+UUID.randomUUID().toString().replace("-","");
  admin.execute("CREATE SCHEMA "+schema);
  String scoped=url+(url.contains("?")?"&":"?")+"currentSchema="+schema;
  var source=new DriverManagerDataSource(scoped,user,password);
  Flyway.configure().dataSource(source).defaultSchema(schema).schemas(schema).locations("classpath:db/migration").load().migrate();
  db=new Db(new JdbcTemplate(source),new ObjectMapper());
  service=new ArchitectureContexts(db,MODEL,PROMPT);tx=new TransactionTemplate(new DataSourceTransactionManager(source));
 }
 @BeforeEach void resetFixtures(){db.jdbc.execute("TRUNCATE TABLE projects CASCADE");}
 @AfterAll static void cleanup(){if(admin!=null && schema!=null)admin.execute("DROP SCHEMA "+schema+" CASCADE");}

 @Test void unifiedSnapshotIsImmutableAndCannotOverwriteNewUploads() throws Exception {
  UUID project=UUID.randomUUID(),scan=UUID.randomUUID(),finding=UUID.randomUUID();String commit="a".repeat(40);
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",project,"test/unified");
  var diagrams=new ArchitectureController(db);diagrams.upload(project,ArchitectureContextsTest.image("png"));
  db.jdbc.update("INSERT INTO scans(id,project_id,repository,branch,commit_sha,workflow_run_id,run_attempt,trigger_type,status,policy_version,policy) VALUES(?,?,'test/unified','main',?,'unified',1,'TEST','QUEUED','test','{}'::jsonb)",scan,project,commit);
  UnifiedReview.snapshot(db,scan,project);var service=new UnifiedReview(db);
  var input=(Map<?,?>)service.input(scan);
  assertEquals("ANALYZING",((Map<?,?>)diagrams.get(project)).get("status"));
  var result=UnifiedReviewTest.result(input.get("diagramId").toString(),input.get("imageSha256").toString(),commit);
  ((ObjectNode)result.path("instructions").get(0)).put("findingId",finding.toString());
  var reports=UnifiedReviewTest.reports();((ObjectNode)reports.get(0)).put("id",finding.toString());
  tx.execute(s->{UnifiedReview.persist(db,scan,result,reports,commit);return null;});
  assertEquals("EXTRACTED",((Map<?,?>)diagrams.get(project)).get("status"));
  service.input(scan);assertEquals("EXTRACTED",((Map<?,?>)diagrams.get(project)).get("status"));
  tx.execute(s->{UnifiedReview.persist(db,scan,result,reports,commit);return null;});
  var changed=result.deepCopy();((ObjectNode)changed.path("architecture")).put("summary","replayed different result");
  assertThrows(IllegalArgumentException.class,()->tx.execute(s->{UnifiedReview.persist(db,scan,changed,reports,commit);return null;}));
  db.jdbc.update("UPDATE scans SET status='COMPLETED',analysis_mode='VLM' WHERE id=?",scan);
  db.jdbc.update("INSERT INTO findings(id,scan_id,rule_id,title,category,severity,file_path,start_line,end_line,fingerprint,confidence,evidence_status) VALUES(?,?,'SEC-02','test','SECURITY','HIGH',?,1,1,'unified','MEDIUM','SUSPECTED')",finding,scan,CodingProposals.TARGET);
  var profile=new ProjectVerificationTest().profile();profile.put("repository","test/unified");
  profile.putArray("editablePaths").add(CodingProposals.TARGET);profile.putArray("contextPaths").add(CodingProposals.TARGET);
  profile.putArray("snapshotPaths").add("backend/app").add("backend/tests");
  ((ObjectNode)profile.path("runtime")).put("workingDirectory","backend");profile.putArray("ruleIds").add("SEC-02");
  db.jdbc.update("INSERT INTO project_verification_profiles(project_id,version,config,config_digest,validated_at) VALUES(?,1,?::jsonb,?,now())",project,profile.toString(),ProjectVerification.digest(profile));
  db.jdbc.update("UPDATE projects SET verification_profile_version=1 WHERE id=?",project);
  var coding=new CodingProposals(db,org.mockito.Mockito.mock(Events.class),true,"test/unified");
  var queued=tx.execute(s->coding.queue(scan,true));assertNull(queued.get("architectureId"));
  var plan=db.json.valueToTree(queued.get("executionPlan"));assertEquals(result,plan.path("unifiedReview"));
  diagrams.upload(project,ArchitectureContextsTest.image("png"));
  UnifiedReview.fail(db,scan);service.input(scan);
  assertEquals("QUEUED",((Map<?,?>)diagrams.get(project)).get("status"));
  assertEquals(input.get("imageSha256"),((Map<?,?>)service.input(scan)).get("imageSha256"));
  var claim=(Map<?,?>)tx.execute(s->coding.claim(new CodingProposals.Claim("test/unified",List.of("python-pytest-v1"),List.of("sha256:"+"a".repeat(64)),List.of(CodingProposals.MODEL))));
  var job=(Map<?,?>)claim.get("job");var handed=(Map<?,?>)job.get("architectureDiagram");
  assertEquals(input.get("diagramId"),handed.get("id"));assertEquals("EXTRACTED",handed.get("status"));
 }

 @Test void durableLifecycleConcurrentClaimsAndCacheVersioning() throws Exception {
  UUID project=UUID.randomUUID();
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",project,"test/architecture");
  var file=ArchitectureContextsTest.image("png");
  var auth=new UsernamePasswordAuthenticationToken("test-reviewer",null);
  var uploaded=(Map<?,?>)tx.execute(status->service.upload(project,file,"a".repeat(40),auth));
  assertEquals("QUEUED",uploaded.get("status"));assertEquals(1,uploaded.get("version"));assertEquals(false,uploaded.get("reused"));
  var duplicate=(Map<?,?>)tx.execute(status->service.upload(project,file,"a".repeat(40),auth));
  assertEquals(uploaded.get("id"),duplicate.get("id"));assertEquals(true,duplicate.get("reused"));
  assertFalse(duplicate.containsKey("imageBytes"));

  var ready=new CountDownLatch(2);var start=new CountDownLatch(1);
  Callable<Map<?,?>> claim=()->{ready.countDown();assertTrue(start.await(5,TimeUnit.SECONDS));return (Map<?,?>)tx.execute(status->service.claim(new ArchitectureContexts.Claim(MODEL,PROMPT)));};
  List<Map<?,?>> claims;
  try(var pool=Executors.newFixedThreadPool(2)){
   var first=pool.submit(claim);var second=pool.submit(claim);assertTrue(ready.await(5,TimeUnit.SECONDS));start.countDown();
   claims=List.of(first.get(10,TimeUnit.SECONDS),second.get(10,TimeUnit.SECONDS));
  }
  assertEquals(1,claims.stream().filter(c->Boolean.TRUE.equals(c.get("available"))).count());
  var claimed=(Map<?,?>)claims.stream().filter(c->Boolean.TRUE.equals(c.get("available"))).findFirst().orElseThrow().get("job");
  assertArrayEquals(file.getBytes(),Base64.getDecoder().decode((String)claimed.get("imageBase64")));
  UUID id=UUID.fromString((String)claimed.get("id"));
  var result=db.json.createObjectNode().put("schemaVersion",1).put("imageSha256",(String)claimed.get("imageSha256"))
   .put("model",MODEL).put("promptVersion",PROMPT).put("diagramType","UNKNOWN").put("summary","Integration fixture is a blank test image");
  for(String field:List.of("components","flows","trustBoundaries","codeHints","assumptions","uncertainties"))result.putArray(field);
  result.putObject("metrics").put("wallDurationMs",1);
  var body=db.json.createObjectNode().put("leaseToken",(String)claimed.get("leaseToken"));body.set("result",result);
  assertEquals(Map.of("status","READY","replayed",false),tx.execute(status->service.complete(id,body)));
  assertEquals(Map.of("status","READY","replayed",true),tx.execute(status->service.complete(id,body.deepCopy())));
  var context=(Map<?,?>)service.context(project,"b".repeat(40));
  assertEquals("COMMIT_MISMATCH",context.get("staleness"));assertEquals(true,context.get("advisoryOnly"));
  assertEquals(true,context.get("available"));

  var changed=new ArchitectureContexts(db,MODEL,"architecture-v2");
  var newVersion=(Map<?,?>)tx.execute(status->changed.upload(project,file,"a".repeat(40),auth));
  assertEquals(2,newVersion.get("version"));assertNotEquals(id.toString(),newVersion.get("id"));
  var newest=(Map<?,?>)service.context(project,"a".repeat(40));
  assertEquals(false,newest.get("available"));assertEquals("QUEUED",newest.get("status"));
  assertEquals(2,((Map<?,?>)newest.get("architecture")).get("version"));
  assertEquals(2,db.count("SELECT count(*) FROM project_architectures WHERE project_id=?",project));
 }

 @Test void directCodingPinsImageWithoutWaitingForGraphExtraction() throws Exception {
  UUID project=UUID.randomUUID(),scan=UUID.randomUUID();String repo="test/"+project;
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",project,repo);
  var auth=new UsernamePasswordAuthenticationToken("test-reviewer",null);
  var testImage=ArchitectureContextsTest.image("png");
  var image=(Map<?,?>)tx.execute(status->service.upload(project,testImage,"a".repeat(40),auth));
  UUID original=UUID.fromString((String)image.get("id"));
  assertEquals("QUEUED",image.get("status"));
  tx.execute(status->service.selectForCoding(project,original));
  db.jdbc.update("INSERT INTO scans(id,project_id,repository,branch,commit_sha,workflow_run_id,run_attempt,trigger_type,status,policy_version,policy) VALUES(?,?,?,'main',?,'direct-test',1,'TEST','COMPLETED','test','{\"bcryptMinCost\":12}'::jsonb)",scan,project,repo,"a".repeat(40));
  db.jdbc.update("INSERT INTO findings(id,scan_id,rule_id,title,category,severity,file_path,start_line,end_line,fingerprint,confidence,evidence_status) VALUES(?,?,'SEC-02','test','SECURITY','HIGH',?,1,1,'test','MEDIUM','SUSPECTED')",UUID.randomUUID(),scan,CodingProposals.TARGET);
  // The current engine requires an activated profile and matching worker capabilities.
  // Seed a test profile; this test verifies image pinning, not real code execution.
  var profile=new ProjectVerificationTest().profile();profile.put("repository",repo);
  profile.putArray("editablePaths").add(CodingProposals.TARGET);
  profile.putArray("contextPaths").add(CodingProposals.TARGET);
  profile.putArray("snapshotPaths").add("backend/app").add("backend/tests");
  ((ObjectNode)profile.path("runtime")).put("workingDirectory","backend");
  profile.putArray("ruleIds").add("SEC-02");
  ProjectVerification.validateConfig(profile);
  db.jdbc.update("INSERT INTO project_verification_profiles(project_id,version,config,config_digest,validated_at) VALUES(?,1,?::jsonb,?,now())",project,profile.toString(),ProjectVerification.digest(profile));
  db.jdbc.update("UPDATE projects SET verification_profile_version=1 WHERE id=?",project);
  var coding=new CodingProposals(db,org.mockito.Mockito.mock(Events.class),true,repo);
  var queued=tx.execute(status->coding.queue(scan,true));
  assertEquals(original.toString(),queued.get("architectureId"));
  var newer=(Map<?,?>)tx.execute(status->service.upload(project,testImage,"b".repeat(40),auth));
  tx.execute(status->service.selectForCoding(project,UUID.fromString((String)newer.get("id"))));
  var claim=(Map<?,?>)tx.execute(status->coding.claim(new CodingProposals.Claim(repo,List.of("python-pytest-v1"),List.of("sha256:"+"a".repeat(64)),List.of(CodingProposals.MODEL))));
  var job=(Map<?,?>)claim.get("job");var handed=(Map<?,?>)job.get("architecture");
  assertEquals(original.toString(),handed.get("id"));
  assertArrayEquals(ArchitectureContextsTest.image("png").getBytes(),Base64.getDecoder().decode((String)handed.get("imageBase64")));
  assertFalse(CodingProposals.publicJob(queued).containsKey("architecture"));
  UUID another=UUID.randomUUID();
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",another,"test/"+another);
  assertThrows(org.springframework.web.server.ResponseStatusException.class,()->tx.execute(status->service.selectForCoding(another,original)));
 }

 @Test void uploadedDiagramFailureRetryAndExpiryPreserveStateBoundaries() throws Exception {
  UUID project=UUID.randomUUID();
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",project,"test/diagram");
  var diagrams=new ArchitectureController(db);
  var uploaded=diagrams.upload(project,ArchitectureContextsTest.image("png"));
  UUID original=(UUID)((Map<?,?>)uploaded.getBody()).get("id");
  tx.execute(status->diagrams.claim(project));
  diagrams.progress(original,new ArchitectureController.Progress("ANALYZING"));
  diagrams.failure(original,new ArchitectureController.Failure("MODEL_TIMEOUT"));
  assertEquals("MODEL_TIMEOUT",((Map<?,?>)diagrams.get(project)).get("errorCode"));
  var retry=(Map<?,?>)diagrams.retry(project,new ArchitectureController.Retry(original));
  UUID next=(UUID)retry.get("id");
  assertNotEquals(original,next);
  var output=new ArchitectureController.Result(List.of(new ArchitectureController.Component("API","service","UNKNOWN","OBSERVED")),"summary");
  assertThrows(org.springframework.web.server.ResponseStatusException.class,()->diagrams.result(original,output));
  assertEquals("QUEUED",((Map<?,?>)diagrams.get(project)).get("status"));
  tx.execute(status->diagrams.claim(project));
  diagrams.progress(next,new ArchitectureController.Progress("ANALYZING"));
  db.jdbc.update("UPDATE architecture_diagrams SET updated_at=now()-interval '40 minutes' WHERE id=?",next);
  assertEquals("WORKER_TIMEOUT",((Map<?,?>)diagrams.get(project)).get("errorCode"));
  assertThrows(org.springframework.web.server.ResponseStatusException.class,()->diagrams.result(next,output));
  UUID finalId=(UUID)((Map<?,?>)diagrams.retry(project,new ArchitectureController.Retry(next))).get("id");
  tx.execute(status->diagrams.claim(project));
  diagrams.progress(finalId,new ArchitectureController.Progress("ANALYZING"));
  diagrams.result(finalId,output);
  assertThrows(org.springframework.web.server.ResponseStatusException.class,()->diagrams.failure(finalId,new ArchitectureController.Failure("BACKEND_UNAVAILABLE")));
  diagrams.expire();
  assertEquals("EXTRACTED",((Map<?,?>)diagrams.get(project)).get("status"));
  UUID queued=UUID.randomUUID();
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",queued,"test/queued");
  diagrams.upload(queued,ArchitectureContextsTest.image("png"));
  db.jdbc.update("UPDATE architecture_diagrams SET updated_at=now()-interval '1 day' WHERE project_id=?",queued);
  diagrams.expire();
  assertEquals("QUEUED",((Map<?,?>)diagrams.get(queued)).get("status"));
 }
}
