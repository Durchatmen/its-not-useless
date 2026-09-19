<script setup>
defineProps({
  /** 引用来源数组，如 ['《临床诊疗指南》', '科室及医生知识库'] */
  sources: { type: Array, default: () => [] },
  /** 免责声明文本，接口要求前端原样展示（接口文档 2.8） */
  disclaimer: { type: String, default: '' },
})
</script>

<template>
  <div v-if="sources.length || disclaimer" class="source-list">
    <div v-if="sources.length" class="sources">
      <span class="label">依据：</span>
      <el-tag v-for="(item, index) in sources" :key="index" size="small" type="info" effect="plain">
        {{ item }}
      </el-tag>
    </div>

    <p v-if="disclaimer" class="disclaimer">{{ disclaimer }}</p>
  </div>
</template>

<style scoped lang="less">
.source-list {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--line);
}

.sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;

  .label {
    font-size: 12px;
    color: var(--text-3);
  }
}

.disclaimer {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
}
</style>
