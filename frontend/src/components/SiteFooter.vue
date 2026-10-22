<template>
  <footer class="site-footer">
    <div class="site-footer__grid">
      <div>
        <RouterLink class="brand brand--footer" to="/">Mộc Store</RouterLink>
        <p>Website thời trang demo. Dữ liệu cửa hàng mẫu, chưa phải thông tin doanh nghiệp chính thức.</p>
      </div>
      <nav aria-label="Thông tin cửa hàng">
        <h2>Khám phá</h2>
        <RouterLink to="/gioi-thieu">Giới thiệu</RouterLink>
        <RouterLink to="/lien-he">Liên hệ</RouterLink>
        <RouterLink to="/cau-hoi-thuong-gap">Câu hỏi thường gặp</RouterLink>
      </nav>
      <nav aria-label="Chính sách">
        <h2>Chính sách</h2>
        <RouterLink to="/chinh-sach-giao-hang">Giao hàng</RouterLink>
        <RouterLink to="/chinh-sach-doi-tra">Đổi trả</RouterLink>
      </nav>
    </div>
    <p class="site-footer__legal">© 2026 Mộc Store — Dự án trình diễn.</p>
  </footer>
</template>
