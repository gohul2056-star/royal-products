public class User {

    private int userId;
    private String name;
    private Library library;

    public User(int userId, String name) {

        this.userId = userId;
        this.name = name;
        this.library = new Library();

    }

    public int getUserId() {
    return userId;
    }

    public String getName() {
    return name;
    }

    public Library getLibrary() {
    return library;
    }

}