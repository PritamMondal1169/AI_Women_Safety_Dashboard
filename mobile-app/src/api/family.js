import api from './index';

export const getFamilyContacts = async () => {
  const response = await api.get('/family');
  return response.data;
};

export const addFamilyContact = async (contactData) => {
  const response = await api.post('/family', contactData);
  return response.data;
};

export const deleteFamilyContact = async (contactId) => {
  const response = await api.delete(`/family/${contactId}`);
  return response.data;
};
