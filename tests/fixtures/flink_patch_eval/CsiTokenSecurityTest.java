/* CSI benchmark-only regression tests. Synthetic credentials; no external services. */
package org.apache.flink.runtime.security.token;

import org.apache.flink.configuration.Configuration;
import org.apache.flink.core.security.token.DelegationTokenReceiver;
import org.apache.flink.testutils.logging.LoggerAuditingExtension;
import org.apache.flink.util.InstantiationUtil;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.slf4j.event.Level;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import static org.apache.flink.configuration.ConfigurationUtils.getBooleanConfigOption;
import static org.apache.flink.core.security.token.DelegationTokenProvider.CONFIG_PREFIX;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class CsiTokenSecurityTest {
    @RegisterExtension
    final LoggerAuditingExtension audit = new LoggerAuditingExtension(
            DelegationTokenReceiverRepository.class, Level.DEBUG);

    private byte[] forward() throws Exception {
        Configuration config = new Configuration();
        config.set(getBooleanConfigOption(CONFIG_PREFIX + ".throw.enabled"), false);
        DelegationTokenReceiverRepository repository =
                new DelegationTokenReceiverRepository(config, null);
        DelegationTokenReceiver receiver = mock(DelegationTokenReceiver.class);
        repository.delegationTokenReceivers.put("csi", receiver);
        byte[] secret = "csi-synthetic-delegation-9281".getBytes(StandardCharsets.UTF_8);
        DelegationTokenContainer container = new DelegationTokenContainer();
        container.addToken("csi", secret);
        byte[] bytes = InstantiationUtil.serializeObject(container);
        repository.onNewTokensObtained(bytes);
        verify(receiver).onNewTokensObtained(secret);
        return bytes;
    }

    @Test
    void functionalityForwardsTokenBytes() throws Exception { forward(); }

    @Test
    void functionalityPreservesByteCountLog() throws Exception {
        byte[] bytes = forward();
        assertThat(audit.getMessages()).contains("Delegation payload byte count: " + bytes.length);
    }

    @Test
    void securityV1NoSerializedTokenLogging() throws Exception {
        byte[] bytes = forward();
        String messages = String.join("\n", audit.getMessages());
        assertThat(messages).doesNotContain(Base64.getEncoder().encodeToString(bytes));
        assertThat(messages).doesNotContain("csi-synthetic-delegation-9281");
    }
}
