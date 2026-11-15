<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import ToastHost from './components/ToastHost.vue'
</script>

<template>
  <div class="min-h-[100dvh] bg-paper">
    <Sidebar />
    <div class="lg:pl-[208px]">
      <main class="mx-auto w-full max-w-[1440px] px-4 pb-20 sm:px-6 lg:px-10">
        <RouterView />
      </main>
    </div>
    <ToastHost />
  </div>
</template>
