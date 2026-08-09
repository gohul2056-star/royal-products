import java.util.ArrayList;

public class Library {

    private ArrayList<Book> books;

    public Library() {
        books = new ArrayList<>();
    }

    public void addBook(Book book) {

        books.add(book);

        System.out.println("Book added successfully!");
    }

    public void displayBooks() {

        if (books.isEmpty()) {
            System.out.println("Library is empty!");
            return;
        }

        System.out.println("\n===== BOOKS =====");

        for (Book book : books) {
            book.displayDetails();
        }
    }

    // Search by ID
    public Book searchBook(int bookId) throws BookNotFoundException {

        for (Book book : books) {

            if (book.getBookId() == bookId) {
                return book;
            }
        }

        throw new BookNotFoundException(
            "Book with ID " + bookId + " was not found."
        );
    }

    // Search by Title
    public Book searchBook(String title) throws BookNotFoundException {

        for (Book book : books) {

            if (book.getTitle().equalsIgnoreCase(title)) {
                return book;
            }
        }

        throw new BookNotFoundException(
            "Book with title " + title + " was not found."
        );
    }

    // Update Book
    public void updateBook(
        int bookId,
        String newTitle,
        String newAuthor
    ) {

        try {

            Book book = searchBook(bookId);

            book.setTitle(newTitle);
            book.setAuthor(newAuthor);

            System.out.println("Book updated successfully!");

        } catch (BookNotFoundException e) {

            System.out.println(e.getMessage());
        }
    }

    // Remove Book
    public void removeBook(int bookId) {

        for (int i = 0; i < books.size(); i++) {

            Book book = books.get(i);

            if (book.getBookId() == bookId) {

                books.remove(i);

                System.out.println("Book removed successfully!");
                return;
            }
        }

        System.out.println("Book not found!");
    }
}