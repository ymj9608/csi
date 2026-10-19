package com.csi;
import org.junit.jupiter.api.Test;import javax.crypto.Mac;import javax.crypto.spec.SecretKeySpec;import java.nio.charset.StandardCharsets;import java.util.HexFormat;import static org.junit.jupiter.api.Assertions.*;
class IntakeTest {
 @Test void rejectsReplayAndTampering()throws Exception{String secret="test-secret-not-used-in-production-000",ts="1700000000";byte[] body="{\"repository\":\"local/demo\"}".getBytes(StandardCharsets.UTF_8);Mac m=Mac.getInstance("HmacSHA256");m.init(new SecretKeySpec(secret.getBytes(),"HmacSHA256"));m.update((ts+".").getBytes());String sig=HexFormat.of().formatHex(m.doFinal(body));assertTrue(Intake.validSignature(body,ts,sig,secret,1700000001));assertFalse(Intake.validSignature(body,ts,sig,secret,1700000400));assertFalse(Intake.validSignature("tampered".getBytes(),ts,sig,secret,1700000001));assertFalse(Intake.validSignature(body,null,null,secret,1700000001));}
 @Test void masksLiteralsAndComments(){String value=Intake.mask("log.info(\"secret-abc\", password); // token: private-value");assertFalse(value.contains("secret-abc"));assertFalse(value.contains("private-value"));assertTrue(value.contains("password"));}
}
