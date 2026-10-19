// Synthetic static-analysis fixture. Never execute this source.
class AccountService {
    private String phoneNumber;
    private String residentRegistrationNo;
    void register(String rawPassword, String accessToken, User user) {
        user.setPassword(rawPassword);
        String passwordHash = DigestUtils.sha256Hex(rawPassword);
        String salt = "synthetic-fixed-salt";
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(10);
        log.info("password={}", rawPassword);
        log.debug("token=" + accessToken);
        userRepository.save(user);
    }
}
