package com.csi;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;

/** Structured scanner observations only; never runtime proof or arbitrary source text. */
public final class EvidenceContext {
    static final Set<String> FIELDS = Set.of("name", "full_name", "phone_number", "resident_registration_no", "date_of_birth", "home_address");
    static final Set<String> CLASSES = Set.of("Signup", "ProfileUpdate", "User", "CsiSignupProfile");
    static void keys(JsonNode n, Set<String> allowed) {
        n.fieldNames().forEachRemaining(k -> { if (!allowed.contains(k)) throw new IllegalArgumentException("Unsupported evidence attribute"); });
    }
    public static JsonNode validate(JsonNode n) {
        if (n == null || n.isMissingNode() || (n.isObject() && n.isEmpty())) return null;
        if (!n.isObject() || n.toString().length() > 8000) throw new IllegalArgumentException("Invalid evidence context");
        keys(n, Set.of("field", "entity", "declarationKind", "runtimeVerified", "signals"));
        if (!FIELDS.contains(n.path("field").asText()) || !CLASSES.contains(n.path("entity").asText())
            || !Set.of("INPUT", "MODEL").contains(n.path("declarationKind").asText())
            || !n.path("runtimeVerified").isBoolean() || n.path("runtimeVerified").asBoolean()
            || !n.path("signals").isArray() || n.path("signals").size() > 8) throw new IllegalArgumentException("Invalid evidence context");
        for (JsonNode s : n.path("signals")) {
            keys(s, Set.of("field", "source", "target", "filePath", "line", "labOnly"));
            String file = s.path("filePath").asText();
            if (!s.path("field").asText().equals(n.path("field").asText())
                || !Set.of("Signup", "ProfileUpdate").contains(s.path("source").asText())
                || !Set.of("User", "CsiSignupProfile").contains(s.path("target").asText())
                || !(n.path("entity").asText().equals(s.path("source").asText()) || n.path("entity").asText().equals(s.path("target").asText()))
                || file.startsWith("/") || file.contains("..") || file.length() > 500 || !file.matches("[A-Za-z0-9_./$-]+\\.py")
                || !s.path("line").isIntegralNumber() || s.path("line").asInt() < 1 || !s.path("labOnly").isBoolean())
                throw new IllegalArgumentException("Invalid storage observation");
        }
        return n;
    }
}
