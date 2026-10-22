<template>
  <section class="hero" aria-labelledby="hero-title">
    <p class="eyebrow">Bộ sưu tập demo</p>
    <h1 id="hero-title">Khám phá phong cách của riêng bạn</h1>
    <p class="hero__copy">
      Nền tảng mua sắm thời trang tiếng Việt đang được xây dựng với trải nghiệm gọn gàng,
      hiện đại và thân thiện trên mọi thiết bị.
    </p>
    <div class="hero__actions">
      <RouterLink class="button button--primary" to="/san-pham">Xem sản phẩm</RouterLink>
      <RouterLink class="button button--secondary" to="/gioi-thieu">Về Mộc Store</RouterLink>
    </div>
  </section>

  <section class="category-preview" aria-labelledby="category-title">
    <div>
      <p class="eyebrow">Danh mục chính</p>
      <h2 id="category-title">Thời trang cho từng khoảnh khắc</h2>
    </div>
    <div class="category-grid">
      <RouterLink to="/danh-muc/ao-thun">Áo thun</RouterLink>
      <RouterLink to="/danh-muc/ao-so-mi">Áo sơ mi</RouterLink>
      <RouterLink to="/danh-muc/ao-khoac">Áo khoác</RouterLink>
      <RouterLink to="/danh-muc/quan-jeans">Quần jeans</RouterLink>
      <RouterLink to="/danh-muc/quan-short">Quần short</RouterLink>
      <RouterLink to="/danh-muc/vay-dam">Váy / Đầm</RouterLink>
      <RouterLink to="/danh-muc/phu-kien">Phụ kiện</RouterLink>
    </div>
  </section>
</template>
