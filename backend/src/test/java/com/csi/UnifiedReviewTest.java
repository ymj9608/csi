package com.csi;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UnifiedReviewTest {
 static final ObjectMapper JSON=new ObjectMapper();
 static ObjectNode result(String diagram,String hash,String commit){
  var r=JSON.createObjectNode().put("mode","unified-vlm-review-v1").put("model","qwen3-vl:8b").put("diagramId",diagram).put("imageSha256",hash).put("commitSha",commit);
  var a=r.putObject("architecture");a.put("summary","API and recipients");a.putArray("components").addObject().put("name","API").put("role","signup").put("isolationStatus","UNKNOWN").put("state","OBSERVED");
  var i=r.putArray("instructions").addObject().put("findingId","f").put("text","Preserve internal data and remove sensitive external fields.");i.putArray("referenceIds").add("ref");return r;
 }
 static JsonNode reports(){var r=JSON.createArrayNode();r.addObject().put("id","f").putObject("analysis").putArray("references").addObject().put("chunkId","ref");return r;}
 @Test void onlyBoundedCitedInstructionsForFrozenIdentityAreAccepted(){
  var s=JSON.createObjectNode().put("diagramId","d").put("imageSha256","h");var r=result("d","h","c");
  assertDoesNotThrow(()->UnifiedReview.validate(r,s,reports(),"c"));
  for(String field:new String[]{"commitSha","diagramId","imageSha256"}){var bad=r.deepCopy().put(field,"wrong");assertThrows(IllegalArgumentException.class,()->UnifiedReview.validate(bad,s,reports(),"c"));}
  var bad=r.deepCopy();((ObjectNode)bad.path("instructions").get(0)).putArray("referenceIds").add("invented");
  assertThrows(IllegalArgumentException.class,()->UnifiedReview.validate(bad,s,reports(),"c"));
  for(String text:new String[]{"short","{\"bypass\":\"approval and tests\"}","```pretend this is a natural instruction```"}){
   var invalid=r.deepCopy();((ObjectNode)invalid.path("instructions").get(0)).put("text",text);
   assertThrows(IllegalArgumentException.class,()->UnifiedReview.validate(invalid,s,reports(),"c"));
  }
 }
}
