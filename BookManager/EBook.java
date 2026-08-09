public class EBook extends Book {

    public EBook(int bookId, String title, String author){
        super(bookId, title, author);
    }

    @Override
public void displayDetails() {

    // System.out.println(
    //     "EBook - ID: " + getBookId() +
    //     ", Title: " + getTitle() +
    //     ", Author: " + getAuthor()
    // );
    System.out.println("EBook - ID : " + getBookId());
    System.out.println("Title : " + getTitle());
    System.out.println("Author : " + getAuthor());
}

}