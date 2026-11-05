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

const productListPage = () => import('../pages/ProductListPage.vue')

export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: HomePage, meta: { title: 'Trang chủ' } },
  {
    path: '/san-pham',
    name: 'products',
    component: productListPage,
    meta: { title: 'Sản phẩm' },
  },
  {
    path: '/danh-muc/:slug',
    name: 'category',
    component: productListPage,
    meta: { title: 'Danh mục sản phẩm' },
  },
  {
    path: '/san-pham/:slug',
    name: 'product-detail',
    component: () => import('../pages/ProductDetailPage.vue'),
    meta: { title: 'Chi tiết sản phẩm' },
  },
  { path: '/gio-hang', name: 'cart', component: () => import('../pages/CartPage.vue'), meta: { title: 'Giỏ hàng' } },
  { path: '/thanh-toan', name: 'checkout', component: () => import('../pages/CheckoutPage.vue'), meta: { title: 'Thanh toán' } },
  { path: '/dat-hang-thanh-cong', name: 'order-success', component: () => import('../pages/OrderSuccessPage.vue'), meta: { title: 'Đặt hàng thành công' } },
  { path: '/tra-cuu-don-hang', name: 'order-lookup', component: () => import('../pages/OrderLookupPage.vue'), meta: { title: 'Tra cứu đơn hàng' } },
  { path: '/don-hang/:orderCode', name: 'order-detail', component: () => import('../pages/OrderDetailPage.vue'), meta: { title: 'Chi tiết đơn hàng' } },
  { path: '/don-hang/:orderCode/thanh-toan-demo', name: 'payment-demo', component: () => import('../pages/OrderDetailPage.vue'), meta: { title: 'Trạng thái thanh toán demo' } },
  { path: '/don-hang/:orderCode/hoan-tien-demo', name: 'refund-demo', component: () => import('../pages/OrderDetailPage.vue'), meta: { title: 'Yêu cầu hoàn tiền mô phỏng' } },
  { path: '/dang-nhap', name: 'login', component: () => import('../pages/LoginPage.vue'), meta: { title: 'Đăng nhập' } },
  placeholder('/dang-ky', 'register', 'Đăng ký', 'Tạo tài khoản khách hàng sẽ được triển khai ở FE-02.'),
  placeholder('/quen-mat-khau', 'forgot-password', 'Quên mật khẩu', 'Luồng đặt lại mật khẩu demo sẽ được triển khai ở FE-02.'),
  placeholder('/dat-lai-mat-khau', 'reset-password', 'Đặt lại mật khẩu', 'Biểu mẫu đặt lại mật khẩu sẽ được triển khai ở FE-02.'),
  { path: '/tai-khoan', name: 'account', component: () => import('../pages/AccountPage.vue'), meta: { title: 'Tài khoản' } },
  placeholder('/tai-khoan/don-hang', 'account-orders', 'Đơn hàng của tôi', 'Lịch sử đơn hàng sẽ được triển khai ở FE-02 và FE-05.'),
  { path: '/tai-khoan/don-hang/:orderCode', name: 'account-order-detail', component: () => import('../pages/OrderDetailPage.vue'), meta: { title: 'Chi tiết đơn hàng' } },
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
