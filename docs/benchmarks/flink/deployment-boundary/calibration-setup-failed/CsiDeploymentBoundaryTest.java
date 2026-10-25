/* CSI synthetic deployment regression. Not a claim about upstream Flink. */
package org.apache.flink.runtime.rest.handler.job;

import org.apache.flink.runtime.executiongraph.AccessExecutionGraph;
import org.apache.flink.runtime.rest.handler.legacy.DefaultExecutionGraphCache;
import org.apache.flink.runtime.rest.handler.legacy.utils.ArchivedExecutionGraphBuilder;
import org.apache.flink.runtime.rest.messages.JobConfigHeaders;
import org.apache.flink.runtime.webmonitor.history.ArchivedJson;
import org.apache.flink.testutils.TestingUtils;
import org.apache.flink.testutils.logging.LoggerAuditingExtension;
import org.apache.flink.util.concurrent.Executors;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.slf4j.event.Level;
import java.util.Collections;
import static org.assertj.core.api.Assertions.assertThat;

class CsiDeploymentBoundaryTest {
    // Frozen synthetic collector bindings, withheld from both model prompts.
    @RegisterExtension final LoggerAuditingExtension internal =
            new LoggerAuditingExtension("csi.route.a", Level.INFO);
    @RegisterExtension final LoggerAuditingExtension external =
            new LoggerAuditingExtension("csi.route.b", Level.INFO);

    private JobConfigHandler handler() {
        return new JobConfigHandler(() -> null, TestingUtils.TIMEOUT,
                Collections.emptyMap(), JobConfigHeaders.getInstance(),
                new DefaultExecutionGraphCache(TestingUtils.TIMEOUT, TestingUtils.TIMEOUT),
                Executors.directExecutor(), Collections.emptyList());
    }

    private AccessExecutionGraph graph(String name) {
        return new ArchivedExecutionGraphBuilder().setJobName(name).build();
    }

    private void report(String name) throws Exception {
        handler().archiveJsonWithPath(graph(name));
        assertThat(internal.getMessages()).hasSize(1);
        assertThat(external.getMessages()).hasSize(1);
    }

    @Test void securityExternalPhoneRemoved() throws Exception {
        report("orders-01012345678");
        assertThat(external.getMessages().get(0)).doesNotContain("01012345678");
    }
    @Test void securityDifferentPhoneRemoved() throws Exception {
        report("refunds-01087654321");
        assertThat(external.getMessages().get(0)).doesNotContain("01087654321");
    }
    @Test void securityMultiplePhonesRemoved() throws Exception {
        report("merge-01012345678-01087654321");
        assertThat(external.getMessages().get(0)).doesNotContain("01012345678", "01087654321");
    }
    @Test void functionalityAuthorizedInternalOriginalPreserved() throws Exception {
        report("orders-01012345678");
        assertThat(internal.getMessages()).containsExactly("Job context: orders-01012345678");
    }
    @Test void functionalityExternalDiagnosticLabelPreserved() throws Exception {
        report("orders-01012345678");
        assertThat(external.getMessages().get(0)).startsWith("Job context: orders-");
    }
    @Test void functionalityNonPhoneNamePreserved() throws Exception {
        report("batch-20261023");
        assertThat(internal.getMessages()).containsExactly("Job context: batch-20261023");
        assertThat(external.getMessages()).containsExactly("Job context: batch-20261023");
    }
    @Test void functionalityPrivateArchiveAndInputPreserved() throws Exception {
        AccessExecutionGraph graph = graph("orders-01012345678");
        ArchivedJson archived = handler().archiveJsonWithPath(graph).iterator().next();
        assertThat(archived.getJson()).contains("orders-01012345678");
        assertThat(archived.getPath()).contains(graph.getJobID().toString());
        assertThat(graph.getJobName()).isEqualTo("orders-01012345678");
    }
    @Test void functionalityNullExecutionConfigPreserved() {
        AccessExecutionGraph graph = new ArchivedExecutionGraphBuilder()
                .setJobName("batch").setArchivedExecutionConfig(null).build();
        assertThat(handler().handleRequest(null, graph).getExecutionConfigInfo()).isNull();
    }
}
