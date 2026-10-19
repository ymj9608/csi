package com.csi;
import org.springframework.web.bind.annotation.*;import org.springframework.http.*;import org.springframework.web.server.ResponseStatusException;import org.springframework.security.core.AuthenticationException;import org.springframework.dao.DataIntegrityViolationException;
import java.util.Map;
@RestControllerAdvice public class Errors {
 @ExceptionHandler(ResponseStatusException.class) ResponseEntity<?> status(ResponseStatusException e){return ResponseEntity.status(e.getStatusCode()).body(Map.of("message",e.getReason()==null?"요청을 처리할 수 없습니다.":e.getReason()));}
 @ExceptionHandler(AuthenticationException.class) ResponseEntity<?> auth(){return ResponseEntity.status(401).body(Map.of("message","로그인 정보를 확인하세요."));}
 @ExceptionHandler(DataIntegrityViolationException.class) ResponseEntity<?> conflict(){return ResponseEntity.status(409).body(Map.of("message","중복되거나 유효하지 않은 데이터입니다."));}
 @ExceptionHandler({IllegalArgumentException.class,org.springframework.http.converter.HttpMessageNotReadableException.class}) ResponseEntity<?> bad(){return ResponseEntity.badRequest().body(Map.of("message","요청 형식을 확인하세요."));}
}
