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
  var coding=new CodingProposals(db,org.mockito.Mockito.mock(Events.class),true,repo);
  var queued=tx.execute(status->coding.queue(scan,true));
  assertEquals(original.toString(),queued.get("architectureId"));
  var newer=(Map<?,?>)tx.execute(status->service.upload(project,testImage,"b".repeat(40),auth));
  tx.execute(status->service.selectForCoding(project,UUID.fromString((String)newer.get("id"))));
  var claim=(Map<?,?>)tx.execute(status->coding.claim(new CodingProposals.Claim(repo)));
  var job=(Map<?,?>)claim.get("job");var handed=(Map<?,?>)job.get("architecture");
  assertEquals(original.toString(),handed.get("id"));
  assertArrayEquals(ArchitectureContextsTest.image("png").getBytes(),Base64.getDecoder().decode((String)handed.get("imageBase64")));
  assertFalse(CodingProposals.publicJob(queued).containsKey("architecture"));
  UUID another=UUID.randomUUID();
  db.jdbc.update("INSERT INTO projects(id,repository,default_branch) VALUES(?,?,'main')",another,"test/"+another);
  assertThrows(org.springframework.web.server.ResponseStatusException.class,()->tx.execute(status->service.selectForCoding(another,original)));
 }
}
