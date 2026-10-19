package com.csi;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;

/** Bounded, authenticated scanner evidence. No source fetch or target execution in the API. */
public final class ChangeSet {
    private static void require(boolean condition) {
        if (!condition) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "유효하지 않은 변경 비교 근거입니다.");
    }
    static String text(JsonNode n, String key, int limit) {
        require(n.path(key).isTextual() && n.path(key).asText().length() <= limit);
        return n.path(key).asText();
    }
    static String path(JsonNode n) {
        String p=text(n,"filePath",500);
        require(!p.startsWith("/") && !p.contains("..") && p.matches("[A-Za-z0-9_./$-]+\\.(java|py)"));
        return p;
    }
    static int number(JsonNode n, String key, int min, int max) {
        require(n.path(key).isIntegralNumber() && n.path(key).canConvertToInt());
        int v=n.path(key).asInt();require(v>=min && v<=max);return v;
    }
    static boolean flag(JsonNode n,String key) {require(n.path(key).isBoolean());return n.path(key).asBoolean();}
    public static void validateReview(JsonNode review, JsonNode source, JsonNode current) {
        require(review.isObject() && review.toString().length()<=200000);
        require(review.path("summaryMode").asText().equals("STATIC_FACTS") && review.path("riskMode").asText().equals("LINKED_FINDING_ANALYSIS"));
        require(review.path("files").isArray() && review.path("files").size()==source.path("files").size());
        require(review.path("references").isArray() && review.path("references").size()<=47);
        Set<String> seen=new HashSet<>(),currentFp=new HashSet<>();current.forEach(f->currentFp.add(f.path("fingerprint").asText()));
        for(var row:review.path("files")) {
            String id=text(row,"changeId",24);require(seen.add(id));JsonNode file=null;
            for(var f:source.path("files"))if(f.path("changeId").asText().equals(id))file=f;
            require(file!=null);String path=file.path("filePath").asText();Set<String> ids=new HashSet<>(),removed=new HashSet<>();
            current.forEach(f->{if(f.path("filePath").asText().equals(path))ids.add(f.path("id").asText());});
            source.path("baselineFindings").forEach(f->{if(f.path("filePath").asText().equals(path)&&!currentFp.contains(f.path("fingerprint").asText()))removed.add(f.path("fingerprint").asText());});
            require(strings(row.path("currentFindingIds")).equals(ids));require(strings(row.path("removedFingerprints")).equals(removed));
            require(row.path("verdict").asText().equals(ids.isEmpty()?"NO_CURRENT_STATIC_CANDIDATES":"REVIEW_REQUIRED"));
        }
    }
    static Set<String> strings(JsonNode array) {
        require(array.isArray() && array.size()<=300);Set<String> result=new HashSet<>();
        for(var n:array){require(n.isTextual() && n.asText().length()<=64 && result.add(n.asText()));}
        return result;
    }
    public static ObjectNode validate(JsonNode n,String head) {
        if(n.isMissingNode()||n.isNull())return null;
        require(n.isObject() && number(n,"schemaVersion",1,1)==1 && head.equals(text(n,"headSha",40)));
        String status=text(n,"status",30);require(Set.of("AVAILABLE","NO_BASE","BASE_UNAVAILABLE").contains(status));
        String base=n.path("baseSha").isNull()?null:text(n,"baseSha",40);
        require(base==null||base.matches("[0-9a-f]{40}"));
        require(status.equals("NO_BASE")?base==null:base!=null);
        require(n.path("files").isArray() && n.path("files").size()<=20);
        require(n.path("baselineFindings").isArray() && n.path("baselineFindings").size()<=300);
        ObjectNode out=JsonNodeFactory.instance.objectNode();out.put("schemaVersion",1).put("headSha",head).put("status",status).put("baseSha",base);
        out.put("totalChangedFiles",number(n,"totalChangedFiles",0,4000));out.put("truncated",flag(n,"truncated"));
        require(out.path("totalChangedFiles").asInt()>=n.path("files").size());
        if(!status.equals("AVAILABLE"))require(n.path("files").isEmpty() && n.path("baselineFindings").isEmpty() && out.path("totalChangedFiles").asInt()==0);
        ArrayNode files=out.putArray("files");Set<String> ids=new HashSet<>(),paths=new HashSet<>();
        for(JsonNode f:n.path("files")) {
            String id=text(f,"changeId",24),p=path(f),kind=text(f,"changeType",12);
            require(id.matches("[a-f0-9]{24}") && ids.add(id) && paths.add(p));
            require(Set.of("ADDED","DELETED","MODIFIED").contains(kind));
            ObjectNode file=files.addObject();file.put("changeId",id).put("filePath",p).put("changeType",kind);
            file.put("addedLines",number(f,"addedLines",0,1000000)).put("removedLines",number(f,"removedLines",0,1000000)).put("truncated",flag(f,"truncated"));
            require(f.path("rows").isArray() && f.path("rows").size()<=100);
            ArrayNode rows=file.putArray("rows");int lastOld=0,lastNew=0;
            for(JsonNode row:f.path("rows")) {
                String tag=text(row,"kind",10);require(Set.of("CONTEXT","ADDED","DELETED","MODIFIED").contains(tag));
                ObjectNode r=rows.addObject();r.put("kind",tag);
                for(String side:List.of("old","new")) {
                    String codeKey=side.equals("old")?"before":"after",lineKey=side+"Line";
                    if(row.path(lineKey).isNull()) {require(row.path(codeKey).isNull());r.putNull(lineKey);r.putNull(codeKey);}
                    else {
                        int line=number(row,lineKey,1,1000000);String code=text(row,codeKey,400);
                        require(code.indexOf('\n')<0 && code.indexOf('\r')<0 && code.indexOf('\u0000')<0);
                        if(side.equals("old")){require(line>lastOld);lastOld=line;}else{require(line>lastNew);lastNew=line;}
                        r.put(lineKey,line).put(codeKey,Intake.mask(code).replaceAll("\\b\\d{7,}\\b","[REDACTED_NUMBER]"));
                    }
                }
                require(!(r.path("oldLine").isNull() && r.path("newLine").isNull()));
                require(tag.equals("ADDED")?r.path("oldLine").isNull():!r.path("oldLine").isNull());
                require(tag.equals("DELETED")?r.path("newLine").isNull():!r.path("newLine").isNull());
            }
            require(f.path("facts").isArray() && f.path("facts").size()<=20);
            ArrayNode facts=file.putArray("facts");Set<String> factIds=new HashSet<>();
            for(JsonNode fact:f.path("facts")) {
                String fid=text(fact,"id",30),type=text(fact,"kind",20),symbol=text(fact,"symbol",130);
                require(fid.matches(id+":[0-9]{1,2}") && factIds.add(fid));
                require(Set.of("FUNCTION_ADDED","FUNCTION_REMOVED","FIELD_ADDED","FIELD_REMOVED").contains(type));
                require(symbol.matches("[A-Za-z_][A-Za-z0-9_]{0,99}(\\.[A-Za-z_][A-Za-z0-9_]{0,99})?"));
                facts.addObject().put("id",fid).put("kind",type).put("symbol",symbol).put("line",number(fact,"line",1,1000000));
            }
        }
        ArrayNode baseline=out.putArray("baselineFindings");Set<String> fingerprints=new HashSet<>();
        for(JsonNode f:n.path("baselineFindings")) {
            String rule=text(f,"ruleId",10),fp=text(f,"fingerprint",64),p=path(f);
            require(Intake.TITLES.containsKey(rule) && fp.matches("[a-f0-9]{64}") && fingerprints.add(fp));
            int start=number(f,"startLine",1,1000000),end=number(f,"endLine",start,start+100);
            baseline.addObject().put("ruleId",rule).put("fingerprint",fp).put("filePath",p).put("startLine",start).put("endLine",end)
                .put("severity",Intake.SEVERITY.get(rule)).put("title",Intake.TITLES.get(rule));
        }
        return out;
    }
}
