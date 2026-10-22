<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useUiStore } from '../stores/ui'

const uiStore = useUiStore()
const { isNavigationOpen } = storeToRefs(uiStore)
</script>

<template>
  <header class="site-header">
    <div class="site-header__inner">
      <RouterLink class="brand" to="/" aria-label="Mộc Store - Trang chủ">
        <span class="brand__mark" aria-hidden="true">M</span>
        <span>Mộc Store</span>
      </RouterLink>

      <button
        class="nav-toggle"
        type="button"
        :aria-expanded="isNavigationOpen"
        aria-controls="primary-navigation"
        @click="uiStore.toggleNavigation"
      >
        <span aria-hidden="true">☰</span>
        <span class="sr-only">Mở hoặc đóng điều hướng</span>
      </button>

      <nav
        id="primary-navigation"
        class="primary-nav"
        :class="{ 'primary-nav--open': isNavigationOpen }"
        aria-label="Điều hướng chính"
      >
        <RouterLink to="/">Trang chủ</RouterLink>
        <RouterLink to="/san-pham">Sản phẩm</RouterLink>
        <RouterLink to="/gioi-thieu">Giới thiệu</RouterLink>
        <RouterLink to="/lien-he">Liên hệ</RouterLink>
        <div class="primary-nav__mobile-actions">
          <RouterLink to="/tai-khoan">Tài khoản</RouterLink>
          <RouterLink to="/gio-hang">Giỏ hàng (0)</RouterLink>
        </div>
      </nav>

      <div class="header-actions" aria-label="Tiện ích">
        <RouterLink to="/tai-khoan">Tài khoản</RouterLink>
        <RouterLink class="cart-link" to="/gio-hang">Giỏ hàng <span aria-hidden="true">(0)</span></RouterLink>
      </div>
    </div>

    <div class="site-header__tools">
      <form class="site-search" action="/san-pham" method="get" role="search">
        <label class="sr-only" for="site-search">Tìm kiếm sản phẩm</label>
        <input id="site-search" name="q" type="search" placeholder="Tìm sản phẩm..." />
        <button type="submit">Tìm kiếm</button>
      </form>

      <nav class="category-nav" aria-label="Danh mục sản phẩm">
        <RouterLink to="/danh-muc/ao-thun">Áo thun</RouterLink>
        <RouterLink to="/danh-muc/ao-so-mi">Áo sơ mi</RouterLink>
        <RouterLink to="/danh-muc/ao-khoac">Áo khoác</RouterLink>
        <RouterLink to="/danh-muc/quan-jeans">Quần jeans</RouterLink>
        <RouterLink to="/danh-muc/quan-short">Quần short</RouterLink>
        <RouterLink to="/danh-muc/vay-dam">Váy / Đầm</RouterLink>
        <RouterLink to="/danh-muc/phu-kien">Phụ kiện</RouterLink>
      </nav>
    </div>
  </header>
</template>
