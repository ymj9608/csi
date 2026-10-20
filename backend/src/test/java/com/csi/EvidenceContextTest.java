package com.csi;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class EvidenceContextTest {
 final ObjectMapper json = new ObjectMapper();
 @Test void acceptsBoundedObservation() throws Exception {
   var n=json.readTree("{\"field\":\"name\",\"entity\":\"User\",\"declarationKind\":\"MODEL\",\"runtimeVerified\":false,\"signals\":[]}");
   assertEquals(n,EvidenceContext.validate(n));
 }
 @Test void rejectsRuntimeProofAndArbitraryText() throws Exception {
   for(String raw: new String[]{"{\"field\":\"name\",\"entity\":\"User\",\"declarationKind\":\"MODEL\",\"runtimeVerified\":true,\"signals\":[]}","{\"secret\":\"do-not-store\"}"}) {
     var n=json.readTree(raw);assertThrows(IllegalArgumentException.class,()->EvidenceContext.validate(n));
   }
 }
 @Test void oldPayloadRemainsSupported() throws Exception {assertNull(EvidenceContext.validate(json.readTree("{}")));}
}
