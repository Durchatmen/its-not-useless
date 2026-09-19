import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as patientApi from '@/api/patients'
import { clearCurrentPatientId, getCurrentPatientId, setCurrentPatientId } from '@/utils/storage'
import { RELATION } from '@/constants/enums'

/** 就诊人列表与当前就诊人 —— 技术选型指定由 Pinia 承载 */
export const usePatientStore = defineStore('patient', () => {
  const patients = ref([])
  const currentPatientId = ref(getCurrentPatientId() || '')
  const loading = ref(false)

  const currentPatient = computed(
    () => patients.value.find((item) => item.patientId === currentPatientId.value) || null,
  )
  /** 本人（relation=SELF），未选择时作为默认就诊人 */
  const selfPatient = computed(
    () => patients.value.find((item) => item.relation === RELATION.SELF) || patients.value[0] || null,
  )

  function selectPatient(patientId) {
    currentPatientId.value = patientId
    setCurrentPatientId(patientId)
  }

  /**
   * 清空就诊人状态。
   * 注意：Pinia 的 $reset() 只对 option store 生效，setup store 必须自己实现。
   */
  function reset() {
    patients.value = []
    currentPatientId.value = ''
    loading.value = false
    clearCurrentPatientId()
  }

  async function fetchPatients() {
    loading.value = true
    try {
      const data = await patientApi.listPatients()
      patients.value = data?.list || data || []
      // 当前就诊人已失效则回落到本人
      const exists = patients.value.some((item) => item.patientId === currentPatientId.value)
      if (!exists && selfPatient.value) selectPatient(selfPatient.value.patientId)
      return patients.value
    } finally {
      loading.value = false
    }
  }

  async function addPatient(payload) {
    const data = await patientApi.createPatient(payload)
    await fetchPatients()
    return data
  }

  async function editPatient(patientId, payload) {
    const data = await patientApi.updatePatient(patientId, payload)
    await fetchPatients()
    return data
  }

  async function removePatient(patientId) {
    await patientApi.removePatient(patientId)
    if (currentPatientId.value === patientId) {
      currentPatientId.value = ''
      clearCurrentPatientId()
    }
    await fetchPatients()
  }

  return {
    patients, currentPatientId, loading,
    currentPatient, selfPatient,
    selectPatient, reset, fetchPatients, addPatient, editPatient, removePatient,
  }
})
