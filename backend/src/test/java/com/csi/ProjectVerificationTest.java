package com.csi;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ProjectVerificationTest {
 final ObjectMapper json=new ObjectMapper();
 ObjectNode profile(){
  var p=json.createObjectNode();p.put("schemaVersion",1).put("profileId","independent-project").put("repository","example/service").put("model",CodingProposals.MODEL).put("generationTimeoutSeconds",300);
  p.putObject("runtime").put("adapter","python-pytest-v1").put("imageId","sha256:"+"a".repeat(64)).put("workingDirectory","service");
  p.putObject("pack").put("id","pii-log-leak-v1").put("sha256","a".repeat(64));p.putObject("driver").put("path","project_profiles/example/driver.py").put("sha256","b".repeat(64));
  p.putArray("editablePaths").add("service/contacts/service.py");p.putArray("contextPaths").add("service/contacts/service.py");p.putArray("snapshotPaths").add("service/contacts").add("service/tests");p.putArray("testPaths").add("tests");
  p.putArray("contracts").add("Preserve storage and validation");p.putArray("ruleIds").add("SEC-05");
  var ids=p.putArray("inventory");for(String n:List.of("test_behavior_preserved","test_invalid_input_rejected","test_no_sensitive_logs","test_useful_log_preserved"))ids.add("tests/test_csi_privacy_pack.py::"+n);
  p.putArray("reproductionTests").add(ids.get(2).asText());p.putArray("relatedFailures");p.putArray("allowedSkips");return p;
 }
 ObjectNode report(ObjectNode p,boolean baseline){
  var r=json.createObjectNode();r.set("inventory",p.path("inventory").deepCopy());r.put("inventoryDigest",ProjectVerification.digest(p.path("inventory"))).put("imageId",p.path("runtime").path("imageId").asText()).put("isolation","DOCKER_NETWORK_NONE").put("exitCode",baseline?1:0);
  var checks=r.putArray("checks");for(var id:p.path("inventory"))checks.addObject().put("id",id.asText()).put("status",baseline&&id.equals(p.path("reproductionTests").get(0))?"FAIL":"PASS");return r;
 }
 @Test void fullIdsSkipsAndDuplicatesAreEnforced(){
  var p=profile();assertDoesNotThrow(()->ProjectVerification.validateConfig(p));assertDoesNotThrow(()->ProjectVerification.gate(p,report(p,true),true));
  assertDoesNotThrow(()->ProjectVerification.gate(p,report(p,false),false));
  for(String status:List.of("SKIP","ERROR","TIMEOUT","FAIL")){var r=report(p,false);((ObjectNode)r.path("checks").get(0)).put("status",status);assertThrows(IllegalArgumentException.class,()->ProjectVerification.gate(p,r,false));}
  var duplicate=report(p,false);((ArrayNode)duplicate.path("checks")).set(0,duplicate.path("checks").get(1));assertThrows(IllegalArgumentException.class,()->ProjectVerification.gate(p,duplicate,false));
  var parameter=report(p,false);((ObjectNode)parameter.path("checks").get(0)).put("id","tests/another.py::TestClass::test_behavior_preserved[other]");assertThrows(IllegalArgumentException.class,()->ProjectVerification.gate(p,parameter,false));
  assertThrows(IllegalArgumentException.class,()->ProjectVerification.gate(p,report(p,false),true));
 }
 @Test void readyRequiresPlanBoundCurrentCandidate(){
  var p=profile();var plan=json.createObjectNode();plan.set("config",p);plan.put("profileVersion",1);plan.putArray("findingIds").add("finding");
  String planDigest=ProjectVerification.digest(plan), content="def store(value):\n    return value\n",after=ProjectVerification.hash(content);
  var job=Map.<String,Object>of("executionPlan",plan,"planDigest",planDigest,"repository","example/service","commitSha","a".repeat(40));
  var r=json.createObjectNode();r.put("schemaVersion",2).put("engineVersion","5").put("profile","independent-project").put("profileVersion",1).put("model",CodingProposals.MODEL).put("repository","example/service").put("commitSha","a".repeat(40)).put("planDigest",planDigest).put("status","READY");
  r.putArray("findingIds").add("finding");r.putArray("referenceIds").add("ref");r.putArray("citedIds").add("finding").add("ref");r.set("testInventory",p.path("inventory"));r.set("allowedSkips",p.path("allowedSkips"));
  r.putObject("sourceHashes").put("service/contacts/service.py","b".repeat(64));r.put("sourceManifestDigest",ProjectVerification.digest(r.path("sourceHashes")));
  var baseline=report(p,true);var checked=report(p,false);for(var v:List.of(baseline,checked)){v.put("planDigest",planDigest).put("sourceManifestDigest",r.path("sourceManifestDigest").asText());}checked.put("candidateSha256",after);
  r.set("baseline",baseline);r.set("verification",checked);r.putArray("attempts").addObject().put("candidateSha256",after).set("verification",checked);
  r.putArray("files").addObject().put("path","service/contacts/service.py").put("content",content).put("beforeSha256","b".repeat(64)).put("afterSha256",after);
  assertDoesNotThrow(()->ProjectVerification.validateResult(r,job,Set.of("finding"),Set.of("ref"),json));
  checked.put("candidateSha256","c".repeat(64));assertThrows(IllegalArgumentException.class,()->ProjectVerification.validateResult(r,job,Set.of("finding"),Set.of("ref"),json));checked.put("candidateSha256",after);
  r.put("planDigest","c".repeat(64));assertThrows(IllegalArgumentException.class,()->ProjectVerification.validateResult(r,job,Set.of("finding"),Set.of("ref"),json));
 }
 @Test void workerMustHaveImageAndModel(){var p=profile();var c=json.createObjectNode();c.putArray("adapters").add("python-pytest-v1");c.putArray("imageIds").add(p.path("runtime").path("imageId").asText());c.putArray("models");assertFalse(ProjectVerification.ready(p,c));((ArrayNode)c.path("models")).add(CodingProposals.MODEL);assertTrue(ProjectVerification.ready(p,c));}
}
