/* CSI benchmark-only regression tests. AWS SDK values are synthetic and local. */
package org.apache.flink.fs.s3.common.token;

import org.apache.flink.configuration.Configuration;
import org.apache.flink.testutils.logging.LoggerAuditingExtension;
import org.apache.flink.util.InstantiationUtil;
import com.amazonaws.services.securitytoken.model.Credentials;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.slf4j.event.Level;
import java.util.Date;
import static org.apache.flink.core.security.token.DelegationTokenProvider.CONFIG_PREFIX;
import static org.assertj.core.api.Assertions.assertThat;

class CsiS3SecurityTest {
    @RegisterExtension
    final LoggerAuditingExtension receiverAudit = new LoggerAuditingExtension(
            AbstractS3DelegationTokenReceiver.class, Level.DEBUG);
    @RegisterExtension
    final LoggerAuditingExtension providerAudit = new LoggerAuditingExtension(
            AbstractS3DelegationTokenProvider.class, Level.DEBUG);

    private void refresh() throws Exception {
        AbstractS3DelegationTokenReceiver receiver = new AbstractS3DelegationTokenReceiver() {
            @Override public String serviceName() { return "s3"; }
        };
        for (int version = 0; version < 2; version++) {
            Credentials value = new Credentials().withAccessKeyId("csi-access-id")
                    .withSecretAccessKey("csi-synthetic-secret-8242")
                    .withSessionToken("csi-synthetic-session-" + version)
                    .withExpiration(new Date(1800000000000L + version));
            receiver.onNewTokensObtained(InstantiationUtil.serializeObject(value));
            assertThat(AbstractS3DelegationTokenReceiver.getCredentials()).isEqualTo(value);
        }
    }

    @Test
    void functionalityRefreshesCredentials() throws Exception { refresh(); }

    @Test
    void functionalityPreservesRefreshEventLog() throws Exception {
        refresh();
        assertThat(receiverAudit.getMessages()).contains("Session credential refresh complete");
    }

    @Test
    void securityV2NoSessionCredentialLogging() throws Exception {
        refresh();
        assertThat(String.join("\n", receiverAudit.getMessages()))
                .doesNotContain("csi-synthetic-session-", "csi-synthetic-secret-8242");
    }

    @Test
    void securityV3NoSecretKeyLogging() {
        AbstractS3DelegationTokenProvider provider = new AbstractS3DelegationTokenProvider() {
            @Override public String serviceName() { return "s3"; }
        };
        Configuration config = new Configuration();
        config.setString(CONFIG_PREFIX + ".s3.region", "us-east-1");
        config.setString(CONFIG_PREFIX + ".s3.access-key", "csi-access-id");
        config.setString(CONFIG_PREFIX + ".s3.secret-key", "csi-synthetic-secret-8242");
        provider.init(config);
        assertThat(provider.delegationTokensRequired()).isTrue();
        assertThat(String.join("\n", providerAudit.getMessages()))
                .doesNotContain("csi-synthetic-secret-8242");
    }
}
