package org.apache.flink.runtime.rest.handler.job;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
class CsiDiagnosticSanitizerTest {
 @Test void handlesNull() { assertThat(JobConfigHandler.sanitizeDiagnosticName(null)).isNull(); }
 @Test void preservesNonPhone() { assertThat(JobConfigHandler.sanitizeDiagnosticName("batch-20261023")).isEqualTo("batch-20261023"); }
 @Test void masksBeginning() { assertThat(JobConfigHandler.sanitizeDiagnosticName("01012345678-orders")).isEqualTo("[REDACTED]-orders"); }
 @Test void masksEmbedded() { assertThat(JobConfigHandler.sanitizeDiagnosticName("orders-01012345678")).isEqualTo("orders-[REDACTED]"); }
 @Test void masksMultiple() { assertThat(JobConfigHandler.sanitizeDiagnosticName("merge-01012345678-01087654321")).isEqualTo("merge-[REDACTED]-[REDACTED]"); }
}
