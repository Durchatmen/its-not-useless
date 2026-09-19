import request from './request'

/* 六大知识库维护（管理员）：科室医生 / 药品 / 检查 / 报告 / 医保 / 诊疗 */

export function listKnowledgeBases() {
  return request.get('/admin/knowledge/bases')
}

export function listKnowledgeDocs(baseKey, params) {
  return request.get(`/admin/knowledge/bases/${baseKey}/documents`, { params })
}

export function uploadKnowledgeDoc(baseKey, formData) {
  return request.post(`/admin/knowledge/bases/${baseKey}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function removeKnowledgeDoc(baseKey, docId) {
  return request.delete(`/admin/knowledge/bases/${baseKey}/documents/${docId}`)
}

/** 重建向量索引 */
export function rebuildKnowledgeIndex(baseKey) {
  return request.post(`/admin/knowledge/bases/${baseKey}/rebuild`)
}
