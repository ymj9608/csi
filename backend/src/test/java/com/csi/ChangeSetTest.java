package com.csi;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChangeSetTest {
 final ObjectMapper json=new ObjectMapper();final String head="b".repeat(40),id="c".repeat(24);
 ObjectNode evidence() throws Exception {
  var n=(ObjectNode)json.readTree("""
   {"schemaVersion":1,"headSha":"HEAD","baseSha":"BASE","status":"AVAILABLE","totalChangedFiles":1,"truncated":false,"files":[{"changeId":"ID","filePath":"a.py","changeType":"MODIFIED","addedLines":1,"removedLines":1,"truncated":false,"rows":[{"kind":"MODIFIED","oldLine":1,"newLine":1,"before":"secret = 'before'","after":"secret = 'after'"}],"facts":[]}],"baselineFindings":[]}
  """.replace("HEAD",head).replace("BASE","a".repeat(40)).replace("ID",id));return n;
 }
 @Test void validatesAndMasks() throws Exception {
  var n=ChangeSet.validate(evidence(),head);assertFalse(n.toString().contains("'before'"));assertTrue(n.toString().contains("REDACTED"));
 }
 @Test void rejectsIdentityPathAndRowMismatch() throws Exception {
  assertThrows(Exception.class,()->ChangeSet.validate(evidence(),"e".repeat(40)));
  var n=evidence();((ObjectNode)n.path("files").get(0)).put("filePath","../a.py");assertThrows(Exception.class,()->ChangeSet.validate(n,head));
  var bad=evidence();((ObjectNode)bad.path("files").get(0).path("rows").get(0)).putNull("oldLine");assertThrows(Exception.class,()->ChangeSet.validate(bad,head));
 }
 @Test void rejectsInventedReviewConnections() throws Exception {
  var source=ChangeSet.validate(evidence(),head);var current=json.readTree("[{\"id\":\"finding\",\"filePath\":\"a.py\",\"fingerprint\":\"fp\"}]");
  var review=(ObjectNode)json.readTree("{\"summaryMode\":\"STATIC_FACTS\",\"riskMode\":\"LINKED_FINDING_ANALYSIS\",\"references\":[],\"files\":[{\"changeId\":\""+id+"\",\"currentFindingIds\":[\"finding\"],\"removedFingerprints\":[],\"verdict\":\"REVIEW_REQUIRED\"}]}");
  assertDoesNotThrow(()->ChangeSet.validateReview(review,source,current));
  ((ArrayNode)review.path("files").get(0).path("currentFindingIds")).removeAll().add("invented");
  assertThrows(Exception.class,()->ChangeSet.validateReview(review,source,current));
 }
}
