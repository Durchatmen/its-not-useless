<script setup>
/**
 * 提醒时间选择 —— 编辑某一种药的服药提醒时间点。
 *
 * 时间点由 API-31 依处方频次算出（如「每6小时一次」→ 00:00/06:00/12:00/18:00），
 * 这里允许用户在此基础上增删改：下拉支持直接输入新时间（allow-create），
 * 下面把算法给的原始时间点列为快捷按钮，避免用户手打。
 */
import { computed } from 'vue'

const props = defineProps({
  /** 当前时间点数组，如 ['08:00', '12:30'] */
  modelValue: { type: Array, default: () => [] },
  /** 接口算出的推荐时间点，作为快捷添加项 */
  options: { type: Array, default: () => [] },
  /** 提示文案，如剂量/频次 */
  hint: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

/** 去重并按时间升序，避免用户加出重复提醒 */
const times = computed(() => [...new Set(props.modelValue)].sort())

const addable = computed(() => props.options.filter((t) => !times.value.includes(t)))

function update(next) {
  emit('update:modelValue', [...new Set(next)].sort())
}

const remove = (time) => update(times.value.filter((t) => t !== time))
const add = (time) => update([...times.value, time])
</script>

<template>
  <div class="time-picker">
    <div v-if="hint" class="hint">{{ hint }}</div>

    <el-select
      :model-value="times"
      multiple
      filterable
      allow-create
      default-first-option
      placeholder="添加提醒时间，如 08:00"
      style="width: 100%"
      @update:model-value="update"
    >
      <el-option v-for="time in times" :key="time" :label="time" :value="time" />
    </el-select>

    <div v-if="addable.length" class="quick">
      <span class="label">快捷添加</span>
      <el-button v-for="time in addable" :key="time" size="small" @click="add(time)">
        + {{ time }}
      </el-button>
    </div>

    <div class="preview">
      <span class="label">已设 {{ times.length }} 个提醒</span>
      <el-tag v-for="time in times" :key="time" closable size="small" @close="remove(time)">
        {{ time }}
      </el-tag>
      <span v-if="!times.length" class="empty">尚未设置提醒时间</span>
    </div>
  </div>
</template>

<style scoped lang="less">
.time-picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hint {
  font-size: 12px;
  color: var(--text-2);
}

.quick {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;

  .label {
    font-size: 12px;
    color: var(--text-3);
  }
}

.preview {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;

  .label {
    font-size: 12px;
    color: var(--text-3);
  }

  .empty {
    font-size: 12px;
    color: var(--text-3);
  }
}
</style>
