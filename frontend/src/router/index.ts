import {
  createRouter,
  createWebHistory,
  type RouterHistory,
  type RouteRecordRaw,
} from 'vue-router'

import HomePage from '../pages/HomePage.vue'
import NotFoundPage from '../pages/NotFoundPage.vue'
import PlaceholderPage from '../pages/PlaceholderPage.vue'

const placeholder = (path: string, name: string, title: string, description: string): RouteRecordRaw => ({
  path,
  name,
  component: PlaceholderPage,
  meta: { title, description },
})

export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: HomePage, meta: { title: 'Trang chủ' } },
  placeholder('/san-pham', 'products', 'Sản phẩm', 'Danh sách, tìm kiếm, lọc và sắp xếp sản phẩm sẽ được triển khai ở FE-03.'),
  placeholder('/danh-muc/:slug', 'category', 'Danh mục sản phẩm', 'Trang danh mục sẽ hiển thị sản phẩm theo nhóm thời trang.'),
  placeholder('/san-pham/:slug', 'product-detail', 'Chi tiết sản phẩm', 'Thông tin sản phẩm, biến thể và sản phẩm liên quan sẽ được bổ sung ở FE-03.'),
  placeholder('/gio-hang', 'cart', 'Giỏ hàng', 'Quản lý sản phẩm và số lượng trong giỏ hàng sẽ được triển khai ở FE-04.'),
  placeholder('/thanh-toan', 'checkout', 'Thanh toán', 'Quy trình đặt hàng sáu bước sẽ được triển khai ở FE-05.'),
  placeholder('/dat-hang-thanh-cong', 'order-success', 'Đặt hàng thành công', 'Trang xác nhận và mã đơn hàng sẽ được triển khai ở FE-05.'),
  placeholder('/dang-nhap', 'login', 'Đăng nhập', 'Đăng nhập bằng email và mật khẩu sẽ được triển khai ở FE-02.'),
  placeholder('/dang-ky', 'register', 'Đăng ký', 'Tạo tài khoản khách hàng sẽ được triển khai ở FE-02.'),
  placeholder('/quen-mat-khau', 'forgot-password', 'Quên mật khẩu', 'Luồng đặt lại mật khẩu demo sẽ được triển khai ở FE-02.'),
  placeholder('/dat-lai-mat-khau', 'reset-password', 'Đặt lại mật khẩu', 'Biểu mẫu đặt lại mật khẩu sẽ được triển khai ở FE-02.'),
  placeholder('/tai-khoan', 'account', 'Tài khoản', 'Thông tin tài khoản khách hàng sẽ được triển khai ở FE-02.'),
  placeholder('/tai-khoan/don-hang', 'account-orders', 'Đơn hàng của tôi', 'Lịch sử đơn hàng sẽ được triển khai ở FE-02 và FE-05.'),
  placeholder('/tai-khoan/don-hang/:orderCode', 'account-order-detail', 'Chi tiết đơn hàng', 'Chi tiết và thao tác hủy đơn hợp lệ sẽ được triển khai ở FE-05.'),
  placeholder('/admin', 'admin-dashboard', 'Quản trị cửa hàng', 'Dashboard quản trị sẽ được triển khai ở FE-06.'),
  placeholder('/admin/san-pham', 'admin-products', 'Quản lý sản phẩm', 'CRUD sản phẩm và biến thể sẽ được triển khai ở FE-06.'),
  placeholder('/admin/don-hang', 'admin-orders', 'Quản lý đơn hàng', 'Quản lý trạng thái đơn hàng sẽ được triển khai ở FE-06.'),
  placeholder('/admin/khach-hang', 'admin-customers', 'Quản lý khách hàng', 'Danh sách khách hàng và lịch sử mua hàng sẽ được triển khai ở FE-06.'),
  placeholder('/admin/ma-giam-gia', 'admin-coupons', 'Quản lý mã giảm giá', 'CRUD mã giảm giá sẽ được triển khai ở FE-06.'),
  placeholder('/admin/noi-dung-rag', 'admin-rag-content', 'Quản lý nội dung RAG', 'FAQ và chính sách cho chatbot sẽ được triển khai ở FE-06.'),
  placeholder('/admin/ho-tro', 'admin-support', 'Yêu cầu hỗ trợ', 'Danh sách ticket và hội thoại liên quan sẽ được triển khai ở FE-06.'),
  placeholder('/gioi-thieu', 'about', 'Giới thiệu', 'Thông tin thương hiệu demo Mộc Store.'),
  placeholder('/lien-he', 'contact', 'Liên hệ', 'Thông tin liên hệ hiển thị tại đây chỉ là dữ liệu mẫu.'),
  placeholder('/chinh-sach-giao-hang', 'shipping-policy', 'Chính sách giao hàng', 'Nội dung chính sách giao hàng mẫu sẽ được cập nhật sau.'),
  placeholder('/chinh-sach-doi-tra', 'return-policy', 'Chính sách đổi trả', 'Nội dung chính sách đổi trả mẫu sẽ được cập nhật sau.'),
  placeholder('/cau-hoi-thuong-gap', 'faq', 'Câu hỏi thường gặp', 'Các câu hỏi thường gặp sẽ được cập nhật từ nội dung quản trị.'),
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage, meta: { title: 'Không tìm thấy trang' } },
]

export const createAppRouter = (history: RouterHistory = createWebHistory()) => {
  const router = createRouter({ history, routes, scrollBehavior: () => ({ top: 0 }) })

  router.afterEach((to) => {
    document.title = `${String(to.meta.title ?? 'Mộc Store')} | Mộc Store`
  })

  return router
}

export default createAppRouter()
