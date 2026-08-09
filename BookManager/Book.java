public abstract class Book implements Borrowable {

    private int bookId;
    private String title;
    private String author;

    public Book(int bookId, String title, String author) {

        this.bookId = bookId;
        this.title = title;
        this.author = author;
    }

    public int getBookId() {
        return bookId;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthor() {
        return author;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public void setAuthor(String author) {
        this.author = author;
    }

    public abstract void displayDetails();

    @Override
    public void borrowBook() {

        System.out.println("Book borrowed: " + title);
    }

    @Override
    public void returnBook() {

        System.out.println("Book returned: " + title);
    }
}