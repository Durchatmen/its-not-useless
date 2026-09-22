<script setup>
/**
 * 就诊人管理（API-04 ~ API-07）。
 *
 * ⚠ 一个必须讲清楚的点：**列表接口返回的 name / idcard / phone 都是脱敏串**
 * （如「张*生」「3301**********1234」，见 schemas/patient.py 的脱敏约定）。
 * 后端 update 的语义是「不传的字段保持原值」，所以回传时必须**跳过带 `*` 的脱敏值**，
 * 否则一保存就把库里的真名真号覆盖成星号 —— 这是本页最容易踩的坑，
 * buildPayload() 里用 `hasMask()` 统一挡掉。
 *
 * 另一个坑：必填字段与文档一致（name / idcard / gender / birthDate / relation），
 * 改身份证号会遇到后端 1002（本账号下已存在）；删除存在未完成挂号单的就诊人返回 2002，
 * 两种错误都由 request.js 的拦截器弹出提示，这里不重复弹。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { GENDER_LABEL, GENDER_OPTIONS, RELATION_LABEL, RELATION_OPTIONS } from '@/constants/patient'
import { usePatientStore } from '@/stores/patient'

const router = useRouter()
const patientStore = usePatientStore()

const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
/** null = 新增，否则为正在编辑的 patientId */
const editingId = ref(null)
const formRef = ref(null)

const BLOOD_TYPES = ['A', 'B', 'O', 'AB', 'Rh阴性', '不详']

function emptyForm() {
  return {
    name: '',
    idcard: '',
    phone: '',
    gender: 'M',
    birthDate: '',
    relation: 'SELF',
    bloodType: '',
    allergyHistory: '',
    medicalHistory: '',
    isDefault: false,
  }
}

const form = reactive(emptyForm())

/** 原始值，用于判断哪些字段用户真的重新输入过 */
let original = { ...emptyForm() }

const isEdit = computed(() => Boolean(editingId.value))

const rules = {
  name: [{ required: true, message: '请填写姓名', trigger: 'blur' }],
  idcard: [
    {
      required: true,
      // 新增必填；编辑时留空表示「不改身份证号」（列表里是脱敏串，不能回传）
      validator: (rule, value, callback) => {
        if (!value) {
          if (isEdit.value) return callback()
          return callback(new Error('请填写身份证号'))
        }
        if (!/^\d{17}[\dXx]$/.test(value)) return callback(new Error('身份证号应为 18 位'))
        return callback()
      },
      trigger: 'blur',
    },
  ],
  gender: [{ required: true, message: '请选择性别', trigger: 'change' }],
  birthDate: [{ required: true, message: '请选择出生日期', trigger: 'change' }],
  relation: [{ required: true, message: '请选择与本人关系', trigger: 'change' }],
}

/** 脱敏串（含 *）不可回传 */
function hasMask(value) {
  return typeof value === 'string' && value.includes('*')
}

/**
 * 组装请求体：只带上「用户真的填过」的字段。
 * name / idcard / phone 在列表里是脱敏串，未重新输入时一律不传
 * （后端语义：不传 = 保持原值）。
 */
function buildPayload() {
  const payload = {
    gender: form.gender,
    birthDate: form.birthDate,
    relation: form.relation,
    bloodType: form.bloodType || null,
    allergyHistory: form.allergyHistory || null,
    medicalHistory: form.medicalHistory || null,
    isDefault: form.isDefault,
  }

  const textFields = ['name', 'idcard', 'phone']
  for (const key of textFields) {
    const value = (form[key] || '').trim()
    if (!value || hasMask(value)) continue
    payload[key] = value
  }

  return payload
}

async function load() {
  loading.value = true
  try {
    await patientStore.fetchPatients()
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  original = { ...emptyForm() }
  dialogVisible.value = true
}

function openEdit(patient) {
  editingId.value = patient.patientId
  const filled = {
    ...emptyForm(),
    name: patient.name || '',
    idcard: patient.idcard || '',
    phone: patient.phone || '',
    gender: patient.gender || 'M',
    birthDate: patient.birthDate || '',
    relation: patient.relation || 'OTHER',
    bloodType: patient.bloodType || '',
    allergyHistory: patient.allergyHistory || '',
    medicalHistory: patient.medicalHistory || '',
    isDefault: Boolean(patient.isDefault),
  }
  Object.assign(form, filled)
  original = { ...filled }
  dialogVisible.value = true
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEdit.value) {
      await patientStore.editPatient(editingId.value, buildPayload())
      ElMessage.success('已保存')
    } else {
      await patientStore.addPatient(buildPayload())
      ElMessage.success('已添加就诊人')
    }
    dialogVisible.value = false
  } catch {
    // 1002 身份证重复 / 2003 校验失败等，拦截器已提示
  } finally {
    submitting.value = false
  }
}

async function remove(patient) {
  try {
    await ElMessageBox.confirm(
      `确定删除就诊人「${patient.name}」吗？删除后其历史挂号与病历仍会保留。`,
      '删除就诊人',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消
  }

  try {
    await patientStore.removePatient(patient.patientId)
    ElMessage.success('已删除')
  } catch {
    // 存在未完成挂号单时后端返回 2002（需先取消挂号），拦截器已提示
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="就诊人管理" subtitle="为自己和家人建档，挂号时选择就诊人">
      <template #extra>
        <el-button type="primary" @click="openCreate">添加就诊人</el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <EmptyState v-if="!loading && !patientStore.patients.length" description="还没有添加就诊人">
        <el-button type="primary" @click="openCreate">添加就诊人</el-button>
      </EmptyState>

      <div v-else class="cards">
        <div
          v-for="item in patientStore.patients"
          :key="item.patientId"
          class="card-item"
          :class="{ active: item.patientId === patientStore.currentPatientId }"
        >
          <div class="head">
            <div class="name-line">
              <strong>{{ item.name }}</strong>
              <el-tag size="small" effect="plain">
                {{ RELATION_LABEL[item.relation] || item.relationDesc || item.relation }}
              </el-tag>
              <el-tag v-if="item.isDefault" size="small" type="success">默认</el-tag>
              <el-tag v-if="item.patientId === patientStore.currentPatientId" size="small" type="warning">
                当前就诊人
              </el-tag>
            </div>
            <div class="actions">
              <el-button
                v-if="item.patientId !== patientStore.currentPatientId"
                size="small"
                text
                type="primary"
                @click="patientStore.selectPatient(item.patientId)"
              >
                设为当前
              </el-button>
              <el-button size="small" text @click="openEdit(item)">编辑</el-button>
              <el-button size="small" text type="danger" @click="remove(item)">删除</el-button>
            </div>
          </div>

          <div class="meta">
            <span>性别：{{ GENDER_LABEL[item.gender] || '—' }}</span>
            <span>出生日期：{{ item.birthDate || '—' }}</span>
            <span>身份证：{{ item.idcard || '—' }}</span>
            <span>手机号：{{ item.phone || '—' }}</span>
            <span>血型：{{ item.bloodType || '—' }}</span>
          </div>

          <div v-if="item.allergyHistory || item.medicalHistory" class="history">
            <p v-if="item.allergyHistory"><span class="label">过敏史</span>{{ item.allergyHistory }}</p>
            <p v-if="item.medicalHistory"><span class="label">既往病史</span>{{ item.medicalHistory }}</p>
          </div>
        </div>
      </div>

      <p class="foot-note">
        列表中的姓名、身份证号、手机号由后端脱敏展示；编辑时未重新填写的脱敏字段不会被覆盖。
      </p>
    </div>

    <!-- 新增 / 编辑 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑就诊人' : '添加就诊人'"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" maxlength="32" placeholder="就诊人真实姓名" />
        </el-form-item>

        <el-form-item label="身份证号" prop="idcard">
          <el-input
            v-model="form.idcard"
            maxlength="18"
            :placeholder="isEdit ? '留空表示不修改（列表显示为脱敏串）' : '18 位身份证号'"
          />
        </el-form-item>

        <el-form-item label="手机号">
          <el-input
            v-model="form.phone"
            maxlength="20"
            :placeholder="isEdit ? '留空表示不修改' : '选填'"
          />
        </el-form-item>

        <el-form-item label="性别" prop="gender">
          <el-radio-group v-model="form.gender">
            <el-radio v-for="opt in GENDER_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="出生日期" prop="birthDate">
          <el-date-picker
            v-model="form.birthDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择出生日期"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="与本人关系" prop="relation">
          <el-select v-model="form.relation" style="width: 100%">
            <el-option
              v-for="opt in RELATION_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="血型">
          <el-select v-model="form.bloodType" clearable placeholder="选填" style="width: 100%">
            <el-option v-for="bt in BLOOD_TYPES" :key="bt" :label="bt" :value="bt" />
          </el-select>
        </el-form-item>

        <el-form-item label="过敏史">
          <el-input v-model="form.allergyHistory" type="textarea" :rows="2" placeholder="如：青霉素过敏" />
        </el-form-item>

        <el-form-item label="既往病史">
          <el-input v-model="form.medicalHistory" type="textarea" :rows="2" placeholder="如：高血压 3 年" />
        </el-form-item>

        <el-form-item label="默认就诊人">
          <el-switch v-model="form.isDefault" />
          <span class="switch-hint">设为默认后，挂号 / 报告等页面会优先选中该就诊人</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
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

.cards {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card-item {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);

  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;

  .name-line {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;

    strong {
      font-size: 16px;
    }
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
  }
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-2);
}

.history {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);

  p {
    font-size: 13px;
    line-height: 1.8;
    color: var(--text-2);
  }

  .label {
    display: inline-block;
    min-width: 60px;
    font-size: 12px;
    color: var(--text-3);
  }
}

.switch-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--text-3);
}

.foot-note {
  margin-top: 16px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}
</style>
