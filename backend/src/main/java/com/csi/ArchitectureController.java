package com.csi;
import org.springframework.web.bind.annotation.*;import org.springframework.web.multipart.MultipartFile;import org.springframework.http.*;import org.springframework.transaction.annotation.Transactional;import java.util.*;
@RestController public class ArchitectureController {
 final Db db;
 public ArchitectureController(Db db){this.db=db;}
 @PostMapping("/api/projects/{id}/architecture") @Transactional public ResponseEntity<?> upload(@PathVariable UUID id,@RequestParam("file") MultipartFile file)throws Exception{
  UUID diagramId=UUID.randomUUID();
  db.jdbc.update("INSERT INTO architecture_diagrams(id,project_id,image,content_type,status,components,summary,confirmed) VALUES(?,?,?,?,'QUEUED',null,null,false) ON CONFLICT(project_id) DO UPDATE SET id=EXCLUDED.id,image=EXCLUDED.image,content_type=EXCLUDED.content_type,status='QUEUED',components=null,summary=null,confirmed=false,updated_at=now()",diagramId,id,file.getBytes(),file.getContentType());
  return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id",diagramId,"status","QUEUED"));
 }
 @GetMapping("/api/projects/{id}/architecture") public Object get(@PathVariable UUID id){
  return db.one("SELECT status,components,summary,confirmed FROM architecture_diagrams WHERE project_id=?",id);
 }
}
