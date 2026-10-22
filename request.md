# Yêu cầu xây dựng website bán quần áo tích hợp chatbot RAG

## 1. Mục tiêu dự án

Xây dựng một website mẫu trình diễn bán quần áo với 100 sản phẩm và tích hợp widget chatbot RAG sử dụng Gemini để hỗ trợ khách hàng.

Website sử dụng tiếng Việt, đơn vị tiền tệ VND, chạy được hoàn chỉnh trên môi trường local và có giao diện responsive cho desktop/mobile.

## 2. Website bán hàng

### 2.1. Phía khách hàng

- Trang chủ, danh mục và trang chi tiết sản phẩm.
- Có đúng 100 sản phẩm demo, bao gồm các nhóm: Áo thun, Áo sơ mi, Áo khoác, Quần jeans, Quần short, Váy/Đầm và Phụ kiện.
- Mỗi sản phẩm có các thông tin cơ bản: tên, mã sản phẩm, mô tả, danh mục, giá, giá khuyến mãi, ảnh, màu sắc, kích cỡ và tồn kho.
- Size mặc định gồm S, M, L, XL; một số sản phẩm có thể có XXL.
- Mỗi sản phẩm có từ 2 đến 4 màu. Tồn kho được quản lý riêng theo từng biến thể màu và size.
- Có nhãn sản phẩm như Mới, Bán chạy và Giảm giá.
- Tìm kiếm sản phẩm theo tên hoặc từ khóa.
- Lọc theo danh mục, khoảng giá, size và màu.
- Sắp xếp theo giá, sản phẩm mới và sản phẩm bán chạy.
- Hiển thị sản phẩm liên quan trên trang chi tiết.
- Giỏ hàng hỗ trợ thêm sản phẩm theo biến thể, thay đổi số lượng và xóa sản phẩm.
- Kiểm tra giá và tồn kho hiện tại trước khi tạo đơn hàng.
- Cho phép khách chưa đăng nhập đặt hàng.
- Người dùng có thể đăng ký, đăng nhập, đăng xuất, quên mật khẩu và xem lịch sử đơn hàng.
- Xác thực mặc định bằng email và mật khẩu; chưa tích hợp đăng nhập mạng xã hội.
- Hỗ trợ nhập và áp dụng mã giảm giá.
- Giao diện responsive, ưu tiên trải nghiệm mobile và bảo đảm vùng tương tác phù hợp trên màn hình cảm ứng.

### 2.2. Quy trình đặt hàng

Quy trình đặt hàng gồm:

1. Xem và cập nhật giỏ hàng.
2. Nhập thông tin người nhận và địa chỉ giao hàng.
3. Xem phí vận chuyển.
4. Chọn phương thức thanh toán.
5. Kiểm tra và xác nhận đơn hàng.
6. Hiển thị trang đặt hàng thành công cùng mã đơn hàng.

Quy tắc mặc định:

- COD là phương thức thanh toán hoạt động hoàn chỉnh.
- Thanh toán online chỉ được mô phỏng trong bản demo, không phát sinh giao dịch thật và không yêu cầu tài khoản sandbox.
- Không tích hợp đơn vị vận chuyển thật.
- Phí vận chuyển là một mức phí cố định và có ngưỡng miễn phí vận chuyển; các giá trị này được cấu hình trong hệ thống.
- Không gửi email thật; trạng thái đặt hàng được hiển thị trực tiếp trên website.
- Kiểm tra tồn kho tại thời điểm xác nhận đơn hàng.
- Trạng thái đơn hàng gồm: Chờ xác nhận, Đã xác nhận, Đang chuẩn bị, Đang giao, Hoàn thành và Đã hủy.
- Khách hàng chỉ được hủy đơn khi đơn chưa chuyển sang trạng thái Đang chuẩn bị.

### 2.3. Trang quản trị

- Có hai vai trò: `customer` và `admin`.
- Admin đăng nhập bằng tài khoản quản trị riêng.
- Dashboard hiển thị số lượng sản phẩm, khách hàng, đơn hàng và doanh thu demo.
- Quản lý sản phẩm: xem, tạo, sửa, xóa, quản lý ảnh, danh mục, giá và nhãn sản phẩm.
- Quản lý biến thể sản phẩm theo màu, size và tồn kho.
- Quản lý đơn hàng: xem chi tiết và cập nhật trạng thái.
- Quản lý khách hàng: xem danh sách và lịch sử mua hàng; không cho phép admin xem hoặc sửa mật khẩu của khách hàng.
- Quản lý mã giảm giá.
- Quản lý nội dung FAQ, bảng size, chính sách giao hàng, đổi trả và khuyến mãi dùng cho chatbot.
- Quản lý các yêu cầu chuyển tiếp sang nhân viên hỗ trợ và xem nội dung hội thoại liên quan.

## 3. Widget chat RAG

### 3.1. Chức năng

- Widget chat nổi trên website và không che các nút thao tác quan trọng trên desktop/mobile.
- Chatbot trả lời dựa trên:
  - Thông tin của 100 sản phẩm.
  - Bảng size.
  - Chính sách giao hàng và đổi trả.
  - Khuyến mãi.
  - FAQ.
- Tìm và đề xuất sản phẩm phù hợp theo nhu cầu, loại sản phẩm, khoảng giá, màu và size của khách hàng.
- Khi đề xuất sản phẩm, chatbot hiển thị thẻ sản phẩm gồm tên, ảnh, giá và link đến trang chi tiết.
- Ghi nhớ ngữ cảnh trong phạm vi một phiên trò chuyện.
- Lưu lịch sử trò chuyện vào database theo session ID.
- Khách hàng không bắt buộc đăng nhập mới có thể sử dụng chatbot.
- Chatbot hỗ trợ tiếng Việt.

### 3.2. Quy tắc truy xuất dữ liệu

- Giá, khuyến mãi, màu, size và tồn kho phải được truy vấn trực tiếp từ PostgreSQL tại thời điểm trả lời, không chỉ lấy từ dữ liệu vector.
- FAQ, bảng size, chính sách giao hàng, đổi trả và nội dung hướng dẫn được embedding và tìm kiếm bằng pgvector.
- Áp dụng truy xuất kết hợp:
  - SQL/filter cho dữ liệu sản phẩm có cấu trúc.
  - Vector search cho câu hỏi ngôn ngữ tự nhiên và tài liệu kiến thức.
- Khi admin cập nhật sản phẩm hoặc tài liệu kiến thức, hệ thống cập nhật embedding tương ứng.
- Tên model Gemini và model embedding được cấu hình bằng biến môi trường, không hard-code trong source code.

### 3.3. Hạn chế chatbot bịa thông tin

- Chatbot chỉ được trả lời dựa trên dữ liệu đã truy xuất được từ hệ thống.
- Chatbot không được tự tạo giá, tồn kho, khuyến mãi, chính sách hoặc thông tin sản phẩm.
- Giá và tồn kho trong câu trả lời phải lấy từ dữ liệu hiện tại trong PostgreSQL.
- Khi không có đủ thông tin, chatbot phải nói rõ rằng chưa tìm thấy dữ liệu thay vì suy đoán.
- Nếu câu hỏi nằm ngoài phạm vi website bán hàng, chatbot lịch sự thông báo giới hạn hỗ trợ.
- Câu trả lời về sản phẩm phải kèm link hoặc thẻ sản phẩm khi có kết quả phù hợp.

### 3.4. Chuyển sang nhân viên hỗ trợ

Trong bản demo, chức năng chuyển sang nhân viên được mô phỏng như sau:

- Khách hàng có thể yêu cầu hỗ trợ từ nhân viên trong widget chat.
- Hệ thống tạo một support ticket trong database và gắn với session chat hiện tại.
- Widget hiển thị mã yêu cầu hỗ trợ cho khách hàng.
- Admin có thể xem danh sách ticket và toàn bộ nội dung hội thoại liên quan.
- Chưa tích hợp live chat, Zalo, Facebook Messenger, email hoặc hotline thật.

## 4. Dữ liệu demo

- Tạo đúng 100 sản phẩm demo bằng tiếng Việt.
- Giá sử dụng đơn vị VND.
- Dữ liệu sản phẩm, danh mục, biến thể, giá và tồn kho được tạo bằng seed script để có thể khởi tạo lại.
- Sử dụng ảnh placeholder hoặc ảnh stock có quyền sử dụng phù hợp cho mục đích demo.
- Ảnh demo được lưu local; chưa sử dụng Cloudinary hoặc S3.
- Tạo dữ liệu mẫu cho bảng size, FAQ, chính sách giao hàng, đổi trả và khuyến mãi.
- Tạo sẵn tài khoản admin demo và một số tài khoản khách hàng demo. Thông tin đăng nhập demo được ghi trong README hoặc seed output, không hard-code mật khẩu production.

## 5. Giao diện và thương hiệu demo

- Sử dụng thương hiệu và logo placeholder, có thể thay đổi sau.
- Phong cách thời trang hiện đại, tối giản và ưu tiên nội dung sản phẩm.
- Sử dụng bảng màu trung tính với một màu nhấn nhất quán.
- Thiết kế mobile-first và responsive cho desktop/mobile.
- Có header, menu danh mục, ô tìm kiếm, giỏ hàng, tài khoản, footer và widget chat nhất quán trên các trang liên quan.
- Các liên kết điều hướng và liên kết footer phải có đích đến hợp lệ, không sử dụng liên kết chết.
- Các thông tin pháp lý, địa chỉ, hotline và chính sách trong bản demo phải được ghi rõ là dữ liệu mẫu nếu chưa được cung cấp chính thức.

## 6. Kiến trúc kỹ thuật

- Frontend: Vue 3 + Vite.
- Backend: Python/FastAPI.
- Database: PostgreSQL.
- Vector database: pgvector chạy trong PostgreSQL.
- LLM: Gemini API; tên model được cấu hình qua biến môi trường.
- Embedding: model embedding tương thích, được cấu hình qua biến môi trường.
- Quản lý ảnh: lưu local trong bản demo.
- Xác thực: email/mật khẩu, tách quyền customer và admin.
- Thanh toán: COD hoàn chỉnh và một phương thức thanh toán online mô phỏng.
- Vận chuyển: phí cố định, không kết nối đơn vị vận chuyển thật.
- Triển khai: local bằng Docker Compose.
- API key, secret và thông tin kết nối database phải đặt trong biến môi trường, không commit vào source code.
- Cung cấp file `.env.example`, database migration, seed script và README hướng dẫn cài đặt/chạy hệ thống.

## 7. Phạm vi không bao gồm trong bản demo

- Thanh toán online hoặc hoàn tiền thật.
- Kết nối đơn vị vận chuyển thật.
- Gửi email, SMS hoặc thông báo đẩy thật.
- Đăng nhập bằng Google, Facebook hoặc mạng xã hội khác.
- Live chat thời gian thực với nhân viên.
- Tích hợp Zalo, Facebook Messenger, hotline hoặc hệ thống CRM bên ngoài.
- Triển khai production, tên miền, SSL, CDN, autoscaling hoặc giám sát production.
- Dữ liệu pháp lý, thông tin doanh nghiệp và chính sách đã được luật sư phê duyệt.

## 8. Tiêu chí nghiệm thu

### 8.1. Khởi chạy hệ thống

- Toàn bộ hệ thống khởi động local theo hướng dẫn trong README.
- Có thể khởi động các thành phần chính bằng Docker Compose.
- Database migration và seed script chạy thành công trên database mới.
- Sau khi seed, hệ thống có đúng 100 sản phẩm demo.
- Có file `.env.example` và không có API key/secret thật trong source code.

### 8.2. Website bán hàng

- Người dùng có thể duyệt danh mục và mở trang chi tiết sản phẩm.
- Tìm kiếm, lọc và sắp xếp trả về kết quả đúng theo dữ liệu.
- Người dùng chọn được biến thể màu/size còn hàng và thêm vào giỏ hàng.
- Người dùng có thể thay đổi số lượng hoặc xóa sản phẩm khỏi giỏ hàng.
- Không thể đặt số lượng vượt quá tồn kho hiện tại.
- Khách chưa đăng nhập có thể hoàn thành một đơn hàng COD.
- Người dùng đã đăng nhập có thể xem lịch sử và chi tiết đơn hàng của mình.
- Mã giảm giá hợp lệ được tính đúng và mã không hợp lệ bị từ chối với thông báo rõ ràng.
- Đơn hàng mới xuất hiện trong trang quản trị.
- Admin có thể cập nhật trạng thái đơn hàng.
- Admin có thể CRUD sản phẩm, biến thể, tồn kho, mã giảm giá và tài liệu RAG.

### 8.3. Chatbot RAG

- Chatbot trả lời được câu hỏi về sản phẩm, bảng size, giao hàng, đổi trả, khuyến mãi và FAQ.
- Chatbot tìm kiếm và đề xuất sản phẩm theo loại, khoảng giá, màu hoặc size.
- Kết quả đề xuất hiển thị đúng tên, ảnh, giá và link sản phẩm.
- Giá và tồn kho chatbot trả lời khớp với dữ liệu hiện tại trong PostgreSQL.
- Chatbot ghi nhớ được ngữ cảnh trong cùng một phiên trò chuyện.
- Khi không tìm thấy dữ liệu, chatbot thông báo không đủ thông tin và không tự bịa câu trả lời.
- Yêu cầu chuyển nhân viên tạo được support ticket và ticket xuất hiện trong trang quản trị.
- Khi admin cập nhật tài liệu kiến thức, nội dung mới có thể được chatbot truy xuất sau khi embedding được cập nhật.

### 8.4. Chất lượng giao diện và kỹ thuật

- Giao diện sử dụng tốt trên desktop và mobile, không bị tràn, chồng lấn hoặc che nút thao tác quan trọng.
- Widget chat không va chạm với các thành phần cố định khác trên mobile.
- Tất cả liên kết nội bộ có đích đến hợp lệ.
- Các trang chính trả về HTTP thành công khi hệ thống đang chạy.
- Browser console không có lỗi JavaScript nghiêm trọng trong các luồng nghiệm thu chính.
- README mô tả rõ cách cấu hình Gemini API, khởi động hệ thống, chạy migration, seed dữ liệu và đăng nhập tài khoản demo.
