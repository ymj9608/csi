package com.csi;
import com.fasterxml.jackson.databind.*;import org.springframework.jdbc.core.JdbcTemplate;import org.springframework.stereotype.Component;import org.springframework.web.server.ResponseStatusException;import org.springframework.http.HttpStatus;import java.util.*;
@Component public class Db {
 final JdbcTemplate jdbc;final ObjectMapper json;public Db(JdbcTemplate j,ObjectMapper m){jdbc=j;json=m;}
 public List<Map<String,Object>> list(String sql,Object...args){return jdbc.query(sql,(rs,n)->{Map<String,Object> row=new LinkedHashMap<>();var meta=rs.getMetaData();for(int i=1;i<=meta.getColumnCount();i++){String k=meta.getColumnLabel(i);StringBuilder name=new StringBuilder();boolean upper=false;for(char c:k.toCharArray()){if(c=='_'){upper=true;continue;}name.append(upper?Character.toUpperCase(c):c);upper=false;}Object v=rs.getObject(i);if(v instanceof java.sql.Timestamp t)v=t.toInstant().toString();else if(v instanceof java.util.UUID)v=v.toString();else if(meta.getColumnType(i)==java.sql.Types.OTHER && v!=null){String raw=rs.getString(i);try{v=json.readValue(raw,Object.class);}catch(Exception e){v=raw;}}row.put(name.toString(),v);}return row;},args);}
 public Map<String,Object> one(String sql,Object...args){var all=list(sql,args);if(all.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"항목을 찾을 수 없습니다.");return all.getFirst();}
 public String encode(Object v){try{return json.writeValueAsString(v);}catch(Exception e){throw new IllegalArgumentException("Invalid JSON");}}
 public long count(String sql,Object...args){return jdbc.queryForObject(sql,Long.class,args);}
 public void log(UUID scan,String event,String component,String level,String message){jdbc.update("INSERT INTO scan_logs(id,scan_id,event_type,component,level,message,trace_id) VALUES(?,?,?,?,?,?,?)",UUID.randomUUID(),scan,event,component,level,message,scan==null?UUID.randomUUID().toString():scan.toString());}
}
