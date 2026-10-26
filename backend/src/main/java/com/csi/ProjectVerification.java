package com.csi;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Project-independent profile registry and verification gates. Legacy proposals remain unchanged. */
@RestController
public class ProjectVerification {
 final Db db;
 public ProjectVerification(Db db){this.db=db;}
 static void require(boolean ok,String message){if(!ok)throw new IllegalArgumentException(message);}
 static String hash(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}
 static JsonNode sorted(JsonNode n){
  if(n.isObject()){var out=JsonNodeFactory.instance.objectNode();var names=new TreeSet<String>();n.fieldNames().forEachRemaining(names::add);for(String k:names)out.set(k,sorted(n.get(k)));return out;}
  if(n.isArray()){var out=JsonNodeFactory.instance.arrayNode();for(var v:n)out.add(sorted(v));return out;}return n;
 }
 static String digest(JsonNode n){return hash(sorted(n).toString());}
 static Set<String> strings(JsonNode n){require(n.isArray(),"Array required");var s=new HashSet<String>();for(var v:n)require(v.isTextual()&&!v.asText().isBlank()&&s.add(v.asText()),"Distinct string IDs required");return s;}
 static void path(String p){require(p.matches("[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*") && Arrays.stream(p.split("/")).noneMatch(s->s.startsWith(".")),"Unsafe profile path");}
 static void validateConfig(JsonNode p){
  require(p.isObject() && p.toString().length()<150000 && p.path("schemaVersion").asInt()==1,"Profile schema");
  require(p.path("profileId").asText().matches("[a-z0-9-]{3,80}"),"Profile identity");
  var runtime=p.path("runtime");require("python-pytest-v1".equals(runtime.path("adapter").asText()),"Unsupported adapter");
  require(runtime.path("imageId").asText().matches("sha256:[a-f0-9]{64}"),"Pinned image required");path(runtime.path("workingDirectory").asText());
  require("pii-log-leak-v1".equals(p.path("pack").path("id").asText()) && p.path("pack").path("sha256").asText().matches("[a-f0-9]{64}"),"Pinned pack required");
  path(p.path("driver").path("path").asText());require(p.path("driver").path("sha256").asText().matches("[a-f0-9]{64}"),"Pinned driver required");
  for(String k:List.of("snapshotPaths","editablePaths","contextPaths","testPaths")){var paths=strings(p.path(k));require(!paths.isEmpty()&&paths.size()<=50,"Profile paths");paths.forEach(ProjectVerification::path);}
  var edits=strings(p.path("editablePaths"));require(edits.size()==1&&edits.iterator().next().endsWith(".py")&&strings(p.path("contextPaths")).containsAll(edits),"Single Python edit required");
  require(!strings(p.path("contracts")).isEmpty()&&!strings(p.path("ruleIds")).isEmpty(),"Behavior contracts required");
  var ids=strings(p.path("inventory"));require(!ids.isEmpty(),"Validated inventory required");
  for(String k:List.of("reproductionTests","relatedFailures","allowedSkips"))require(ids.containsAll(strings(p.path(k))),"Unknown test ID");
  var pack=Set.of("tests/test_csi_privacy_pack.py::test_no_sensitive_logs","tests/test_csi_privacy_pack.py::test_useful_log_preserved","tests/test_csi_privacy_pack.py::test_behavior_preserved","tests/test_csi_privacy_pack.py::test_invalid_input_rejected");
  require(ids.containsAll(pack)&&!Collections.disjoint(pack,strings(p.path("reproductionTests")))&&Collections.disjoint(pack,strings(p.path("allowedSkips"))),"Security pack required");
  require(CodingProposals.MODEL.equals(p.path("model").asText())&&p.path("generationTimeoutSeconds").asInt()>=30&&p.path("generationTimeoutSeconds").asInt()<=300,"Execution budget");
 }
 static void gate(JsonNode p,JsonNode report,boolean baseline){
  require("DOCKER_NETWORK_NONE".equals(report.path("isolation").asText()) && p.path("runtime").path("imageId").equals(report.path("imageId")),"Verification environment");
  var expected=strings(p.path("inventory"));require(expected.equals(strings(report.path("inventory")))&&digest(p.path("inventory")).equals(report.path("inventoryDigest").asText()),"Test inventory changed");
  var checks=report.path("checks");require(checks.isArray()&&checks.size()==expected.size(),"Complete test results required");
  Set<String> seen=new HashSet<>(),failures=new HashSet<>();var skips=strings(p.path("allowedSkips"));
  for(var c:checks){String id=c.path("id").asText(),status=c.path("status").asText();require(expected.contains(id)&&seen.add(id),"Duplicate or unknown test");
   require(Set.of("PASS","FAIL","SKIP").contains(status),"Test harness error");
   if(status.equals("SKIP"))require(skips.contains(id),"Required test skipped");
   if(status.equals("FAIL"))failures.add(id);
  }
  if(baseline){var allowed=new HashSet<>(strings(p.path("reproductionTests")));allowed.addAll(strings(p.path("relatedFailures")));
   require(!Collections.disjoint(failures,strings(p.path("reproductionTests")))&&allowed.containsAll(failures)&&report.path("exitCode").asInt(-1)==1,"Invalid baseline reproduction");
  }else require(failures.isEmpty()&&report.path("exitCode").asInt(-1)==0,"All required tests must pass");
 }
 @GetMapping("/api/projects/{id}/verification-profiles") public Object list(@PathVariable UUID id){return db.list("SELECT * FROM project_verification_profiles WHERE project_id=? ORDER BY version DESC",id);}
 @PostMapping("/api/projects/{id}/verification-profiles") @Transactional public Object create(@PathVariable UUID id,@RequestBody JsonNode config){
  validateConfig(config);var project=db.one("SELECT * FROM projects WHERE id=? FOR UPDATE",id);
  require(Objects.equals(project.get("repository"),config.path("repository").asText()),"Repository mismatch");String digest=digest(config);
  var found=db.list("SELECT * FROM project_verification_profiles WHERE project_id=? AND config_digest=?",id,digest);if(!found.isEmpty())return found.getFirst();
  int version=(int)db.count("SELECT coalesce(max(version),0)+1 FROM project_verification_profiles WHERE project_id=?",id);
  db.jdbc.update("INSERT INTO project_verification_profiles(project_id,version,config,config_digest) VALUES(?,?,?::jsonb,?)",id,version,config.toString(),digest);
  return Map.of("projectId",id,"version",version,"configDigest",digest,"status","DRAFT");
 }
 @PostMapping("/internal/projects/{id}/verification-profiles/{version}/validate") @Transactional public Object validate(@PathVariable UUID id,@PathVariable int version,@RequestBody JsonNode body){
  var row=db.one("SELECT * FROM project_verification_profiles WHERE project_id=? AND version=? FOR UPDATE",id,version);
  var config=db.json.valueToTree(row.get("config"));require(Objects.equals(row.get("configDigest"),body.path("configDigest").asText()),"Profile digest mismatch");
  var validation=body.path("validation");require(validation.path("commitSha").asText().matches("[a-f0-9]{40}"),"Commit required");
  require(digest(validation.path("sourceManifest")).equals(validation.path("sourceManifestDigest").asText()),"Manifest digest");gate(config,validation.path("baseline"),true);
  if(row.get("validation")!=null)require(db.json.valueToTree(row.get("validation")).equals(validation),"Validation is immutable");
  else db.jdbc.update("UPDATE project_verification_profiles SET validation=?::jsonb,validated_at=now() WHERE project_id=? AND version=?",validation.toString(),id,version);
  return Map.of("status","VALIDATED");
 }
 @PostMapping("/api/projects/{id}/verification-profiles/{version}/activate") @Transactional public Object activate(@PathVariable UUID id,@PathVariable int version){
  var row=db.one("SELECT * FROM project_verification_profiles WHERE project_id=? AND version=?",id,version);
  if(row.get("validatedAt")==null)throw new ResponseStatusException(HttpStatus.CONFLICT,"Worker의 격리 원본 검증이 필요합니다.");
  db.jdbc.update("UPDATE projects SET verification_profile_version=? WHERE id=?",version,id);return Map.of("status","ACTIVE","version",version);
 }
 JsonNode active(Object projectId){
  var rows=db.list("SELECT v.* FROM projects p JOIN project_verification_profiles v ON v.project_id=p.id AND v.version=p.verification_profile_version WHERE p.id=?",UUID.fromString(projectId.toString()));
  return rows.isEmpty()?null:db.json.valueToTree(rows.getFirst());
 }
 static boolean matches(JsonNode config,Map<String,Object> f){return strings(config.path("editablePaths")).contains(f.get("filePath"))&&strings(config.path("ruleIds")).contains(f.get("ruleId"));}
 @PostMapping("/internal/coding-workers/heartbeat") public Object heartbeat(@RequestBody JsonNode body){
  require(body.path("repository").asText().matches("[\\w.-]+/[\\w.-]+"),"Repository required");strings(body.path("adapters"));strings(body.path("models"));strings(body.path("imageIds"));require(body.toString().length()<50000,"Capabilities too large");
  db.jdbc.update("INSERT INTO coding_workers(repository,capabilities) VALUES(?,?::jsonb) ON CONFLICT(repository) DO UPDATE SET capabilities=excluded.capabilities,seen_at=now()",body.path("repository").asText(),body.toString());return Map.of("status","CONNECTED");
 }
 static boolean ready(JsonNode c,JsonNode capability){return capability.path("adapters").isArray()&&strings(capability.path("adapters")).contains(c.path("runtime").path("adapter").asText())&&strings(capability.path("imageIds")).contains(c.path("runtime").path("imageId").asText())&&strings(capability.path("models")).contains(c.path("model").asText());}
 @GetMapping("/api/projects/{id}/coding-capabilities") public Object capabilities(@PathVariable UUID id){
  var p=db.one("SELECT repository FROM projects WHERE id=?",id);var active=active(id);var out=new LinkedHashMap<String,Object>();out.put("profile",active);
  var workers=db.list("SELECT capabilities,seen_at FROM coding_workers WHERE repository=? AND seen_at>now()-interval '45 seconds'",p.get("repository"));
  out.put("workerReady",active!=null&&!workers.isEmpty()&&ready(active.path("config"),db.json.valueToTree(workers.getFirst().get("capabilities"))));return out;
 }
 @GetMapping("/api/coding-proposals/{id}/verification") public Object verification(@PathVariable UUID id){return db.list("SELECT attempt,report FROM coding_verification_runs WHERE proposal_id=? ORDER BY attempt",id);}
 static void validateResult(JsonNode r,Map<String,Object> job,Set<String> findingIds,Set<String> references,ObjectMapper json){
  var plan=json.valueToTree(job.get("executionPlan"));var p=plan.path("config");validateConfig(p);
  require(r.toString().length()<500000&&r.path("schemaVersion").asInt()==2&&r.path("engineVersion").asText().equals("5"),"Result schema");
  require(Objects.equals(job.get("planDigest"),r.path("planDigest").asText())&&digest(plan).equals(r.path("planDigest").asText()),"Plan mismatch");
  require(Objects.equals(job.get("repository"),r.path("repository").asText())&&Objects.equals(job.get("commitSha"),r.path("commitSha").asText())&&p.path("model").equals(r.path("model")),"Job context");
  require(p.path("profileId").equals(r.path("profile"))&&plan.path("profileVersion").equals(r.path("profileVersion")),"Profile identity");
  require(strings(plan.path("findingIds")).equals(strings(r.path("findingIds")))&&findingIds.containsAll(strings(r.path("findingIds")))&&references.containsAll(strings(r.path("referenceIds"))),"Evidence context");
  require(p.path("inventory").equals(r.path("testInventory"))&&p.path("allowedSkips").equals(r.path("allowedSkips")),"Inventory binding");
  require(r.path("sourceHashes").isObject()&&digest(r.path("sourceHashes")).equals(r.path("sourceManifestDigest").asText()),"Source manifest");
  String status=r.path("status").asText();require(Set.of("READY","BLOCKED").contains(status),"Result status");
  require(r.path("attempts").isArray()&&r.path("attempts").size()<=2,"Attempt budget");
  if(status.equals("BLOCKED")){require(r.path("files").isArray()&&r.path("files").isEmpty(),"Blocked result has patch");return;}
  gate(p,r.path("baseline"),true);gate(p,r.path("verification"),false);
  require(r.path("attempts").size()>0,"Verified attempt required");var attempt=r.path("attempts").get(r.path("attempts").size()-1);
  require(attempt.path("verification").equals(r.path("verification")),"Final attempt binding");
  String target=p.path("editablePaths").get(0).asText();var files=r.path("files");require(files.isArray()&&files.size()==1&&target.equals(files.get(0).path("path").asText()),"Edit scope");
  var f=files.get(0);String content=f.path("content").asText(),after=hash(content);
  require(content.getBytes(StandardCharsets.UTF_8).length>=20&&content.getBytes(StandardCharsets.UTF_8).length<=32000&&after.equals(f.path("afterSha256").asText()),"Candidate digest");
  require(f.path("beforeSha256").asText().matches("[a-f0-9]{64}")&&f.path("beforeSha256").equals(r.path("sourceHashes").path(target))&&!f.path("beforeSha256").asText().equals(after),"Source identity");
  require(after.equals(r.path("verification").path("candidateSha256").asText())&&after.equals(attempt.path("candidateSha256").asText()),"Stale verification");
  for(String field:List.of("planDigest","sourceManifestDigest"))require(r.path(field).equals(r.path("baseline").path(field))&&r.path(field).equals(r.path("verification").path(field)),"Verification binding");
  var cites=strings(r.path("citedIds"));var allowed=new HashSet<>(findingIds);allowed.addAll(references);
  require(allowed.containsAll(cites)&&!Collections.disjoint(cites,findingIds)&&!Collections.disjoint(cites,references),"Citations required");
  if(plan.hasNonNull("unifiedReview")){
   var h=r.path("handoff");require("unified-vlm-review-v1".equals(h.path("mode").asText())&&"READY".equals(h.path("status").asText())&&h.path("reusedScanAnalysis").asBoolean(),"Saved VLM handoff required");
   require(digest(plan.path("unifiedReview")).equals(h.path("reviewDigest").asText())&&plan.path("commitSha").equals(h.path("commitSha"))&&plan.path("unifiedReview").path("imageSha256").equals(h.path("imageSha256")),"Saved VLM review binding");
   List<String> tasks=new ArrayList<>();for(var task:plan.path("unifiedReview").path("instructions")){List<String> ids=new ArrayList<>();task.path("referenceIds").forEach(x->ids.add(x.asText()));tasks.add(task.path("findingId").asText()+": "+task.path("text").asText()+"\nReferences: "+String.join(", ",ids));}
   require(String.join("\n\n",tasks).equals(h.path("instruction").asText()),"Saved VLM instruction changed");
   UnifiedReview.validateFlowHandoff(plan.path("unifiedReview"),h);
  }
  if(job.get("architectureId")!=null){var h=r.path("handoff");require(Objects.equals(job.get("architectureId"),h.path("architectureId").asText())&&"READY".equals(h.path("status").asText())&&"vlm-orchestrator-v1".equals(h.path("mode").asText()),"VLM orchestration required");
   boolean delegated=false,checked=false,finished=false;for(var t:h.path("trace"))if("OK".equals(t.path("status").asText())){switch(t.path("tool").asText()){case "delegate_coding"-> {delegated=true;checked=false;finished=false;}case "run_verification"->checked=delegated;case "finish_review"->finished=checked;default->{}}}require(finished,"VLM verified review required");
  }
 }
}
