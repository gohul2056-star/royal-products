import java.util.InputMismatchException;
import java.util.Scanner;

public class Main {

    public static void main(String[] args) {

        Scanner scanner = new Scanner(System.in);

        User user = new User(1, "Jeeva");

        Library library = user.getLibrary();

        System.out.println("Welcome, " + user.getName());

        while (true) {

            System.out.println("\n===== BOOK MANAGER =====");
            System.out.println("1. Add Book");
            System.out.println("2. Display Books");
            System.out.println("3. Search Book");
            System.out.println("4. Update Book");
            System.out.println("5. Remove Book");
            System.out.println("6. Borrow Book");
            System.out.println("7. Return Book");
            System.out.println("8. Exit");

            int choice;

            try {

                System.out.print("Enter your choice: ");
                choice = scanner.nextInt();

            } catch (InputMismatchException e) {

                System.out.println("Please enter a number!");
                scanner.nextLine();
                continue;
            }

            switch (choice) {

                // =========================
                // 1. ADD BOOK
                // =========================
                case 1:

                    System.out.println("\n===== ADD BOOK =====");

                    System.out.print("Enter Book ID: ");
                    int bookId = scanner.nextInt();

                    scanner.nextLine();

                    System.out.print("Enter Book Title: ");
                    String title = scanner.nextLine();

                    System.out.print("Enter Author: ");
                    String author = scanner.nextLine();

                    Book book = new EBook(
                        bookId,
                        title,
                        author
                    );

                    library.addBook(book);

                    break;

                // =========================
                // 2. DISPLAY BOOKS
                // =========================
                case 2:

                    library.displayBooks();

                    break;

                // =========================
                // 3. SEARCH BOOK
                // =========================
                case 3:

                    System.out.println("\n===== SEARCH BOOK =====");
                    System.out.println("1. Search by ID");
                    System.out.println("2. Search by Title");

                    System.out.print("Enter your choice: ");
                    int searchChoice = scanner.nextInt();

                    scanner.nextLine();

                    if (searchChoice == 1) {

                        System.out.print("Enter Book ID: ");
                        int searchId = scanner.nextInt();

                        try {

                            Book foundBook = library.searchBook(searchId);

                            System.out.println("\nBook Found!");

                            foundBook.displayDetails();

                        } catch (BookNotFoundException e) {

                            System.out.println(e.getMessage());
                        }

                    } else if (searchChoice == 2) {

                        System.out.print("Enter Book Title: ");
                        String searchTitle = scanner.nextLine();

                        try {

                            Book foundBook =
                                library.searchBook(searchTitle);

                            System.out.println("\nBook Found!");

                            foundBook.displayDetails();

                        } catch (BookNotFoundException e) {

                            System.out.println(e.getMessage());
                        }

                    } else {

                        System.out.println("Invalid search choice!");
                    }

                    break;

                // =========================
                // 4. UPDATE BOOK
                // =========================
                case 4:

                    System.out.println("\n===== UPDATE BOOK =====");

                    System.out.print("Enter Book ID to update: ");
                    int updateId = scanner.nextInt();

                    scanner.nextLine();

                    System.out.print("Enter New Title: ");
                    String newTitle = scanner.nextLine();

                    System.out.print("Enter New Author: ");
                    String newAuthor = scanner.nextLine();

                    library.updateBook(
                        updateId,
                        newTitle,
                        newAuthor
                    );

                    break;

                // =========================
                // 5. REMOVE BOOK
                // =========================
                case 5:

                    System.out.println("\n===== REMOVE BOOK =====");

                    System.out.print("Enter Book ID to remove: ");
                    int removeId = scanner.nextInt();

                    library.removeBook(removeId);

                    break;

                // =========================
                // 6. BORROW BOOK
                // =========================
                case 6:

                    System.out.println("\n===== BORROW BOOK =====");

                    System.out.print("Enter Book ID: ");
                    int borrowId = scanner.nextInt();

                    try {

                        Book bookToBorrow =
                            library.searchBook(borrowId);

                        bookToBorrow.borrowBook();

                    } catch (BookNotFoundException e) {

                        System.out.println(e.getMessage());
                    }

                    break;

                // =========================
                // 7. RETURN BOOK
                // =========================
                case 7:

                    System.out.println("\n===== RETURN BOOK =====");

                    System.out.print("Enter Book ID: ");
                    int returnId = scanner.nextInt();

                    try {

                        Book bookToReturn =
                            library.searchBook(returnId);

                        bookToReturn.returnBook();

                    } catch (BookNotFoundException e) {

                        System.out.println(e.getMessage());
                    }

                    break;

                // =========================
                // 8. EXIT
                // =========================
                case 8:

                    System.out.println(
                        "Thank you for using Book Manager!"
                    );

                    scanner.close();
                    return;

                // =========================
                // INVALID CHOICE
                // =========================
                default:

                    System.out.println("Invalid choice!");
            }
        }
    }
}

