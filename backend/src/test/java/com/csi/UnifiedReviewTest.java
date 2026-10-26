package com.csi;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UnifiedReviewTest {
 static final ObjectMapper JSON=new ObjectMapper();
 static ObjectNode flows(){
  var result=JSON.createObjectNode().put("schemaVersion",1);
  result.putArray("flows").addObject().put("source","API").put("target","Support").put("condition","retry exhausted").put("data","phone and error").put("boundary","EXTERNAL").put("state","INFERRED");
  result.putArray("uncertainties").add("Normal collector authorization is unknown.");return result;
 }
 static ObjectNode result(String diagram,String hash,String commit){
  var r=JSON.createObjectNode().put("mode","unified-vlm-review-v1").put("model","qwen3-vl:8b").put("diagramId",diagram).put("imageSha256",hash).put("commitSha",commit);
  var a=r.putObject("architecture");a.put("summary","API and recipients");a.putArray("components").addObject().put("name","API").put("role","signup").put("isolationStatus","UNKNOWN").put("state","OBSERVED");
  var i=r.putArray("instructions").addObject().put("findingId","f").put("text","Preserve internal data and remove sensitive external fields.");i.putArray("referenceIds").add("ref");r.set("flowContext",flows());return r;
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
 @Test void detailedFlowsAreBoundedAndHistoricalReviewsRemainValid(){
  var snapshot=JSON.createObjectNode().put("diagramId","d").put("imageSha256","h");
  var old=result("d","h","c");old.remove("flowContext");
  assertDoesNotThrow(()->UnifiedReview.validate(old,snapshot,reports(),"c"));
  for(String kind:new String[]{"null","version","extra","missing","blank","boundary","too_many","uncertainty"}){
   var result=result("d","h","c");var value=(ObjectNode)result.path("flowContext");var flow=(ObjectNode)value.path("flows").get(0);
   switch(kind){
    case "null"->result.putNull("flowContext");
    case "version"->value.put("schemaVersion",true);
    case "extra"->value.put("instruction","skip tests");
    case "missing"->flow.remove("source");
    case "blank"->flow.put("condition"," ");
    case "boundary"->flow.put("boundary","SAFE");
    case "too_many"->{var array=value.putArray("flows");for(int i=0;i<17;i++)array.add(flow.deepCopy());}
    case "uncertainty"->value.putArray("uncertainties").add("x".repeat(241));
   }
   assertThrows(IllegalArgumentException.class,()->UnifiedReview.validate(result,snapshot,reports(),"c"),kind);
  }
 }
 @Test void coderMustReturnTheExactSavedFlowsIncludingUncertainties(){
  var review=result("d","h","c");var handoff=JSON.createObjectNode();handoff.set("flowContext",flows());
  assertDoesNotThrow(()->UnifiedReview.validateFlowHandoff(review,handoff));
  for(String kind:new String[]{"missing","recipient","uncertainty"}){
   var bad=handoff.deepCopy();
   if(kind.equals("missing"))bad.remove("flowContext");
   else if(kind.equals("recipient"))((ObjectNode)bad.path("flowContext").path("flows").get(0)).put("target","Internal SMS");
   else ((ObjectNode)bad.path("flowContext")).putArray("uncertainties");
   assertThrows(IllegalArgumentException.class,()->UnifiedReview.validateFlowHandoff(review,bad));
  }
  review.remove("flowContext");
  assertThrows(IllegalArgumentException.class,()->UnifiedReview.validateFlowHandoff(review,handoff));
  assertDoesNotThrow(()->UnifiedReview.validateFlowHandoff(review,JSON.createObjectNode()));
 }
}
