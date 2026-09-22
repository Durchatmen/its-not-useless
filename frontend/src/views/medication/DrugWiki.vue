<script setup>
/**
 * 药品百科。
 *
 * 说明一个设计取舍：后端没有独立的药品库接口（药品只作为处方的 DrugItem 存在，
 * 没有 t_drug 表，也没有 /drugs 路由），所以本页不假装有一个全量药品库，
 * 而是把**你处方上的药**做成可检索的用药参考：说明书要点、禁忌、医保类型、疗程。
 * 想了解处方以外的药，走「问 AI 医生」—— 药品知识库问答由 AI 侧（RAG）承担。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import * as prescriptionApi from '@/api/prescriptions'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'

const router = useRouter()

const loading = ref(false)
const prescription = ref(null)
const keyword = ref('')

const drugs = computed(() => {
  const all = prescription.value?.drugs || []
  const key = keyword.value.trim()
  if (!key) return all
  return all.filter(
    (drug) =>
      drug.drugName?.includes(key) ||
      drug.instructions?.includes(key) ||
      drug.contraindication?.includes(key),
  )
})

const INSURANCE_TAG = { 甲类: 'success', 乙类: 'warning', 丙类: 'info' }

async function load() {
  loading.value = true
  try {
    prescription.value = await prescriptionApi.getCurrentPrescription({})
  } finally {
    loading.value = false
  }
}

/**
 * 处方以外的用药问题交给 AI 助手。
 * AIChat 目前只认 query.symptom 这个预填参数（见 views/ai/AIChat.vue），
 * 这里沿用它把问题预填进对话框，不新增前端路由参数。
 */
function askAi(drug) {
  router.push({
    name: 'AiChat',
    query: { symptom: `请解释药品「${drug.drugName}」的用法用量、禁忌和注意事项` },
  })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="药品百科" subtitle="你处方上每种药的用法用量、禁忌与医保类型">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'MedicationPlan' })">
          返回用药计划
        </el-button>
      </template>
    </PageHeader>

    <div class="panel">
      <div class="search">
        <el-input
          v-model="keyword"
          placeholder="搜索药品名称、用法或禁忌"
          clearable
          style="max-width: 320px"
        />
        <span class="count">共 {{ drugs.length }} 种药</span>
      </div>

      <div v-loading="loading" class="list">
        <EmptyState
          v-if="!loading && !drugs.length"
          :description="keyword ? '没有匹配的药品' : '暂无处方药品'"
        >
          <el-button type="primary" @click="router.push({ name: 'MedicationPlan' })">
            去看看我的处方
          </el-button>
        </EmptyState>

        <div v-for="drug in drugs" :key="drug.drugId" class="drug">
          <div class="drug-head">
            <div class="name-line">
              <h3>{{ drug.drugName }}</h3>
              <el-tag v-if="drug.insuranceType" size="small" :type="INSURANCE_TAG[drug.insuranceType] || 'info'">
                {{ drug.insuranceType }}
              </el-tag>
            </div>
            <el-button size="small" text type="primary" @click="askAi(drug)">问 AI 医生</el-button>
          </div>

          <p v-if="drug.specification" class="spec">规格：{{ drug.specification }}</p>

          <div class="tags">
            <el-tag v-if="drug.dosage" size="small" effect="plain">单次 {{ drug.dosage }}</el-tag>
            <el-tag v-if="drug.frequency" size="small" effect="plain">{{ drug.frequency }}</el-tag>
            <el-tag v-if="drug.usage" size="small" effect="plain">{{ drug.usage }}</el-tag>
            <el-tag v-if="drug.days" size="small" effect="plain">疗程 {{ drug.days }} 天</el-tag>
          </div>

          <div class="sections">
            <div v-if="drug.instructions" class="section">
              <span class="label">用法用量</span>
              <p>{{ drug.instructions }}</p>
            </div>
            <div v-if="drug.contraindication" class="section warn">
              <span class="label">禁忌与副作用</span>
              <p>{{ drug.contraindication }}</p>
            </div>
            <div v-if="!drug.instructions && !drug.contraindication" class="section">
              <p class="none">该药暂无说明书要点，可点「问 AI 医生」进一步了解。</p>
            </div>
          </div>
        </div>
      </div>

      <p class="foot-note">
        本页信息取自你的处方数据，仅作用药参考，具体用药请遵医嘱。
      </p>
    </div>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
}

.panel {
  padding: 20px;
  .card();
}

.search {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line);

  .count {
    font-size: 13px;
    color: var(--text-2);
  }
}

.list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 120px;
}

.drug {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.drug-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  .name-line {
    display: flex;
    align-items: center;
    gap: 8px;

    h3 {
      font-size: 16px;
      font-weight: 600;
    }
  }
}

.spec {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.sections {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}

.section {
  margin-bottom: 10px;

  .label {
    font-size: 12px;
    color: var(--text-3);
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    line-height: 1.7;
    color: var(--text-2);
  }

  &.warn p {
    color: #b45309;
  }

  .none {
    color: var(--text-3);
  }
}

.foot-note {
  margin-top: 18px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}
</style>
