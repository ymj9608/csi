package com.csi;
import com.fasterxml.jackson.core.type.TypeReference;import org.springframework.stereotype.Component;import org.springframework.beans.factory.annotation.Value;import java.nio.file.*;import java.util.*;
@Component public class PolicyCatalog {
 final Map<String,Object> policy;final List<Map<String,Object>> catalog;
 public PolicyCatalog(Db db,@Value("${csi.policy-file}")String p,@Value("${csi.catalog-file}")String c)throws Exception{policy=db.json.readValue(Files.readString(Path.of(p)),new TypeReference<>(){});catalog=db.json.readValue(Files.readString(Path.of(c)),new TypeReference<>(){});}
}
