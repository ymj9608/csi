/* CSI benchmark-only regression tests; uses the upstream local test keystore. */
package org.apache.flink.runtime.net;

import org.apache.flink.configuration.Configuration;
import org.apache.flink.configuration.SecurityOptions;
import org.apache.flink.testutils.logging.LoggerAuditingExtension;
import org.apache.flink.shaded.netty4.io.netty.buffer.UnpooledByteBufAllocator;
import org.apache.flink.shaded.netty4.io.netty.handler.ssl.ClientAuth;
import org.apache.flink.shaded.netty4.io.netty.handler.ssl.SslContext;
import org.apache.flink.shaded.netty4.io.netty.handler.ssl.SslProvider;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.slf4j.event.Level;
import javax.net.ssl.SSLEngine;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CsiSslSecurityTest {
    @RegisterExtension
    final LoggerAuditingExtension audit = new LoggerAuditingExtension(SSLUtils.class, Level.DEBUG);

    private String endpoint(boolean enabled) throws Exception {
        Configuration config = new Configuration();
        config.set(SecurityOptions.SSL_REST_ENABLED, true);
        config.set(SecurityOptions.SSL_REST_VERIFY_HOSTNAME, enabled);
        SslContext context = SSLUtils.createRestNettySSLContext(
                config, true, ClientAuth.NONE, SslProvider.JDK);
        SSLEngine engine = context.newEngine(UnpooledByteBufAllocator.DEFAULT, "localhost", 443);
        return engine.getSSLParameters().getEndpointIdentificationAlgorithm();
    }

    @Test
    void securityV4HonorsExplicitHostnameVerification() throws Exception {
        assertThat(endpoint(true)).isEqualTo("HTTPS");
    }

    @Test
    void functionalityHonorsExplicitDisabledSetting() throws Exception {
        assertThat(endpoint(false)).isNullOrEmpty();
    }

    @Test
    void securityV5NoKeystorePasswordLoggingOnFailure() {
        String secret = "csi-synthetic-invalid-keystore-7351";
        Configuration config = new Configuration();
        config.set(SecurityOptions.SSL_REST_ENABLED, true);
        config.set(SecurityOptions.SSL_REST_KEYSTORE,
                CsiSslSecurityTest.class.getResource("/local127.keystore").getFile());
        config.set(SecurityOptions.SSL_REST_KEYSTORE_PASSWORD, secret);
        config.set(SecurityOptions.SSL_REST_KEY_PASSWORD, secret);
        assertThatThrownBy(() -> SSLUtils.createRestNettySSLContext(
                config, false, ClientAuth.NONE, SslProvider.JDK)).isInstanceOf(Exception.class);
        assertThat(String.join("\n", audit.getMessages())).doesNotContain(secret);
    }

    @Test
    void functionalityPreservesRedactedDiagnostic() {
        Configuration config = new Configuration();
        config.set(SecurityOptions.SSL_REST_ENABLED, true);
        config.set(SecurityOptions.SSL_REST_KEYSTORE,
                CsiSslSecurityTest.class.getResource("/local127.keystore").getFile());
        config.set(SecurityOptions.SSL_REST_KEYSTORE_PASSWORD, "invalid-synthetic-password");
        config.set(SecurityOptions.SSL_REST_KEY_PASSWORD, "invalid-synthetic-password");
        assertThatThrownBy(() -> SSLUtils.createRestNettySSLContext(
                config, false, ClientAuth.NONE, SslProvider.JDK)).isInstanceOf(Exception.class);
        assertThat(audit.getMessages()).contains("Keystore diagnostic: [REDACTED]");
    }
}
