// Synthetic remediation fixture. No runtime or attack execution.
class AccountService {
    private String email;
    void register(String rawPassword, User user) {
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(12);
        user.setPasswordHash(encoder.encode(rawPassword));
        log.info("event=SIGNUP_STARTED");
        userRepository.save(user);
    }
    String checksum(byte[] fileBytes) {
        return DigestUtils.sha256Hex(fileBytes);
    }
}
