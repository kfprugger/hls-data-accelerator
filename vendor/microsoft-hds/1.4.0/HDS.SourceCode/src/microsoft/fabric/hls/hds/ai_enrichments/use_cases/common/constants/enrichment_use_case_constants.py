# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------




from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.fhir_resource_transform_config import FHIRResourceTransformConfig


class EnrichmentUseCaseConstants:
    """
    This class contains constants for enrichment use cases.
    """
    DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS = 10
    DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE = 25
    UNSPECIFIED_MAPPING = "sdoh-category-unspecified"

    
    FOOD_INSECURITY_MAPPING = {
        "Food insecurity:Experiencing hunger": "food-insecurity",
        "Food insecurity:Lack of access to healthy food options": "food-insecurity",
        "Food insecurity:Inability to afford food": "food-insecurity",
    }

    HOUSING_INSTABILITY_MAPPING = {
        "Housing instability:Facing homelessness or inadequate housing": "inadequate-housing",
        "Housing instability:Risk of foreclosure, feeling isolated, or experiencing social exclusion": "social-connection",
        "Housing instability:Living with pests, mold, or in an unsafe area": "material-hardship",
        "Housing instability:Affected by environmental factors such as pollution, noise, or light pollution": "material-hardship",
        "Housing instability:Experiencing multiple moves": "housing-instability",
    }

    TRANSPORTATION_INSECURITY_MAPPING = {
        "Transportation insecurity:Lack of transportation or unreliable mode of transportation": "transportation-insecurity",
        "Transportation insecurity:Difficulty accessing care": "transportation-insecurity",
    }

    SOCIOECONOMIC_MAPPING = {
        "Socioeconomic:Unemployment or unstable employment status": "employment-status",
        "Socioeconomic:Experiencing financial strain": "financial-insecurity",
        "Socioeconomic:Lack of insurance": "health-insurance-coverage-status",
        "Socioeconomic:Lack of family or community support": "social-connection",
        "Socioeconomic:Limited education": "educational-attainment",
    }
    
    UTILITIES_MAPPING = {
        "Utilities:Experiencing shut off of electric, gas, oil, or water services": "utility-insecurity",
    }

    CONVERSATIONAL_ENRICHMENT_TERMINOLOGY_MAPPING = {
        "system": "https://hl7.org/fhir/us/sdoh-clinicalcare/STU2.2/CodeSystem-SDOHCC-CodeSystemTemporaryCodes.html",
        "name": "FHIR",
        "code_mappings": {
            **FOOD_INSECURITY_MAPPING,
            **HOUSING_INSTABILITY_MAPPING,
            **TRANSPORTATION_INSECURITY_MAPPING,
            **SOCIOECONOMIC_MAPPING,
            **UTILITIES_MAPPING
        }
    }
    
    SDOH_ENRICHMENT_MODEL_INSTRUCTIONS = {
    "use_case_name": "SDOH",
    "system_message": "You are an expert in identifying Social Determinants of Health (SDOH) data from a transcript between a patient and a provider. Only identify the SDOH factor categories and subcategories if it is explicitly and clearly stated in the transcript that it is affecting the patient negatively. Do not infer or assume any factors that are not directly mentioned. SDOH Categories and Subcategories:\n1. Food insecurity\n    1.1 Experiencing hunger\n    1.2 Lack of access to healthy food options\n    1.3 Inability to afford food\n2. Interpersonal safety\n    2.1 Suffering from physical abuse\n    2.2 Enduring verbal abuse\n    2.3 Feeling threatened\n    2.4 Experiencing violence\n3. Housing instability\n    3.1 Facing homelessness or inadequate housing\n    3.2 Risk of foreclosure, feeling isolated, or experiencing social exclusion\n    3.3 Living with pests, mold, or in an unsafe area\n    3.4 Affected by environmental factors such as pollution, noise, or light pollution\n    3.5 Experiencing multiple moves\n4. Transportation insecurity\n    4.1 Lack of transportation or unreliable mode of transportation\n    4.2 Difficulty accessing care.",
    "examples": [
        {
            "user": {
                "role": "user",
                "content": "Doctor: Good morning, how are you feeling today?\n\nPatient: Good morning, Doctor. I’m doing okay, just a bit stressed.\n\nDoctor: I’m sorry to hear that. I see you’re here for a follow-up on your hypertension. How have you been managing your blood pressure?\n\nPatient: It’s been a bit up and down. I try to take my medication regularly, but the stress isn’t helping.\n\nDoctor: Stress can definitely impact your blood pressure. Can you tell me more about what’s been stressing you out?\n\nPatient: Well, I have a place to live right now, but I’m really worried about losing it in the future. My landlord mentioned that they might sell the building, and I don’t know where I would go if that happens.\n\nDoctor: That sounds very stressful. Housing stability is really important for your overall health, especially when managing a condition like hypertension. Have you looked into any resources or support that might be available to help you if you need to find a new place?\n\nPatient: Not yet. I don’t even know where to start.\n\nDoctor: I understand. There are community organizations and housing assistance programs that can help. I can provide you with some information on those. In the meantime, how is your living situation affecting your daily life and health?\n\nPatient: It’s hard to focus on anything else. I’m constantly worried about the future, and it’s affecting my sleep and my ability to concentrate at work.\n\nDoctor: It’s important to address these concerns. Let’s work together to find some resources that can help you feel more secure. Also, we can discuss some strategies to manage your stress and improve your sleep, which will help with your blood pressure as well."
            },
            "assistant": {
                "enrichmentResult": [
                    {"value":"Housing instability:Facing homelessness or inadequate housing", "domain": "SDOH", "reasoning": "The patient is worried about losing their current place of residence due to the possibility of the building being sold by the landlord."},
                    {"value":"Housing instability:Risk of foreclosure, feeling isolated, or experiencing social exclusion","domain": "SDOH", "reasoning": "The patient feels isolated and unsure of where to start looking for resources or support in case they need to find a new place to live."},
                    {"value":"Socioeconomic:Experiencing financial strain","domain": "SDOH", "reasoning": "The patient’s worry about potentially losing their home suggests possible financial strain."}
                ]
            }
        },
        {
            "user": {
                "role": "user",
                "content": "Doctor: Hello, how can I assist you today?\n\nPatient: Hi Doctor, I’ve been feeling very stressed and I think it’s affecting my health.\n\nDoctor: I’m sorry to hear that. Can you tell me more about what’s been causing your stress?\n\nPatient: I lost my job a few months ago, and it’s been really tough finding a new one. I’m worried about making ends meet and I don’t have health insurance anymore.\n\nDoctor: That sounds very challenging. Unemployment and financial strain can have a significant impact on your health. Have you been able to access any support or resources during this time?\n\nPatient: I’ve tried looking for job assistance programs, but it’s been overwhelming and I don’t have much support from family or friends.\n\nDoctor: It’s important to address these concerns. There are community resources that can help with job placement and financial support. I can help connect you to some of these services. In the meantime, how has this situation been affecting your day-to-day life?\n\nPatient: It’s really hard to focus on anything else. I’m constantly worried and it’s affecting my sleep and my ability to look for work effectively.\n\nDoctor: Let’s work on finding some resources to help with your employment and financial situation, and also discuss strategies to manage your stress and improve your sleep. This should help with your overall well-being."
            },
            "assistant": {
                "enrichmentResult": [
                {
                    "value": "Socioeconomic:Unemployment or unstable employment status",
                    "domain": "employment-status",
                    "reasoning": "The patient lost their job and is struggling to find new employment."
                },
                {
                    "value": "Socioeconomic:Experiencing financial strain",
                    "domain": "financial-insecurity",
                    "reasoning": "The patient is worried about making ends meet after losing their job."
                },
                {
                    "value": "Socioeconomic:Lack of insurance",
                    "domain": "health-insurance-coverage-status",
                    "reasoning": "The patient no longer has health insurance after losing their job."
                },
                {
                    "value": "Socioeconomic:Lack of family or community support",
                    "domain": "social-connection",
                    "reasoning": "The patient has limited support from family or friends during this challenging time."
                },
                {
                    "value": "Socioeconomic:Limited education",
                    "domain": "educational-attainment",
                    "reasoning": "The patient may have limited education, which could be impacting their ability to find new employment."
                }
                ]
            }
        }
     ],
     "terminology": CONVERSATIONAL_ENRICHMENT_TERMINOLOGY_MAPPING
    }

    # Configuration for sentiment analysis use case
    SENTIMENT_ENRICHMENT_MODEL_INSTRUCTIONS = {
    "use_case_name": "SENTIMENT",
    "system_message": "You are an assist in interpreting transcriptions between healthcare providers and patients, offering detailed sentiment analysis for the patient. Evaluate the final sentiment of the patient and clarify the sentiment based ONLY on the following aspects: Doctor Services: Evaluate the patient's sentiment towards the quality of care provided by doctors, including communication and clarity, empathy and compassion, professionalism and respect, responsiveness and attentiveness, confidence and competence, support and reassurance, and outcome and follow-up. Note that a patient can have a positive interaction with the doctor even if their health is declining. Staff Services: Assess the patient's sentiment regarding the services provided by the hospital staff, including scheduling, wait times, professionalism and courtesy, responsiveness and attentiveness, communication and information, and support and assistance. Hospital Facilities: Analyze the patient's sentiment towards the hospital's facilities, including cleanliness and hygiene, comfort and amenities, accessibility and navigation, safety and security, technology and equipment, and overall environment. Cost/Insurance: Evaluate the patient's sentiment regarding the costs of services and interactions with insurance, including affordability, insurance coverage, billing process, financial assistance, and insurance interactions. For each aspect, provide the final sentiment as POSITIVE, NEGATIVE, or NEUTRAL by analyzing all sentiments per each aspect. If the sentiment is NEGATIVE, provide a detailed explanation by quoting the actual conversation in the reasoning. POSITIVE sentiment: Indicates the patient's satisfaction with the aspect. NEGATIVE sentiment: Indicates the patient's dissatisfaction with the aspect. NEUTRAL sentiment: Indicates the patient's ambivalence or lack of strong feelings regarding the aspect. Return the output in JSON format as shown in the examples below. Always include Doctor Services as required aspect with analyzing sentiment with reasoning & result and for other optional aspects if transcript does not contain any information then do not include in response. Please assist in providing analysis for transcript content decorated between ##INPUT## only",
    "examples": [
        {
            "user": {
                "role": "user",
                "content": "Doctor: Good morning, how are you feeling today? Patient: Good morning, Doctor. I’m doing okay, just a bit stressed. Doctor: I’m sorry to hear that. I see you’re here for a follow-up on your hypertension. How have you been managing your blood pressure? Patient: It’s been a bit up and down. I try to take my medication regularly, but the stress isn’t helping. Doctor: Stress can definitely impact your blood pressure. Can you tell me more about what’s been stressing you out? Patient: Well, I have a place to live right now, but I’m really worried about losing it in the future. My landlord mentioned that they might sell the building, and I don’t know where I would go if that happens. Doctor: That sounds very stressful. Housing stability is really important for your overall health, especially when managing a condition like hypertension. Have you looked into any resources or support that might be available to help you if you need to find a new place? Patient: Not yet. I don’t even know where to start. Doctor: I understand. There are community organizations and housing assistance programs that can help. I can provide you with some information on those. In the meantime, how is your living situation affecting your daily life and health? Patient: It’s hard to focus on anything else. I’m constantly worried about the future, and it’s affecting my sleep and my ability to concentrate at work. Doctor: It’s important to address these concerns. Let’s work together to find some resources that can help you feel more secure. Also, we can discuss some strategies to manage your stress and improve your sleep, which will help with your blood pressure as well."
            },
            "assistant": {
                "enrichmentResult": [
                    {"domain": "SENTIMENT:DoctorServices", "reasoning": "The patient is compliant with the physician's instructions regarding medication adjustments and acknowledges the need for increased dosage. The patient also appreciates the detailed review of their health status and the physician's advice on managing their conditions.", "value": "POSITIVE"}
                ]
            }
        },
        {
					"user": {
						"role": "user",
						"content": "Doctor: Good morning! How are you feeling today? Patient: Good morning, Doctor. I'm feeling a bit better, thank you. Your treatment has been really effective. Doctor: I'm glad to hear that. It's always our goal to help our patients feel better as quickly as possible. Is there anything else I can assist you with today? Patient: No, your services have been excellent. However, I did have some issues with the hospital staff. They were quite rude and unhelpful. Doctor: I'm really sorry to hear that. I'll make sure to address this with the hospital administration. Your feedback is important to us. Patient: Thank you, Doctor. Also, I noticed that some of the hospital facilities are not well-maintained. It made my stay here quite uncomfortable. Doctor: I apologize for that as well. We are working on improving our facilities. Your comfort is very important to us. Patient: I appreciate that. On a different note, I found the cost of the treatment to be reasonable, and my insurance covered most of it, which was a relief. Doctor: I'm glad to hear that the cost and insurance aspects were manageable for you. If you have any more concerns or questions, please feel free to let me know. Patient: Thank you, Doctor. I really appreciate your help and understanding."
					},
					"assistant": {
						"enrichmentResult": [
							{
								"domain": "SENTIMENT:DoctorServices",
								"reasoning": "The patient expresses satisfaction with the doctor's treatment and appreciates the doctor's help and understanding. The patient states, 'Your treatment has been really effective' and 'your services have been excellent.'",
								"value": "POSITIVE"
							},
							{
								"domain": "SENTIMENT:StaffServices",
								"reasoning": "The patient mentions issues with the hospital staff, describing them as 'quite rude and unhelpful.'",
								"value": "NEGATIVE"
							},
							{
								"domain": "SENTIMENT:HospitalFacilities",
								"reasoning": "The patient notes that some of the hospital facilities are 'not well-maintained' and that it made their stay 'quite uncomfortable.'",
								"value": "NEGATIVE"
							},
							{
								"domain": "SENTIMENT:CostInsurance",
								"reasoning": "The patient found the cost of the treatment to be reasonable and mentions that their insurance covered most of it, which was a relief.",
								"value": "POSITIVE"
							}
						]
					}
		},
        {
            "user": {
                "role": "user",
                "content": "Doctor: Hello, how have you been feeling since your last visit? Patient: Hi, Doctor. I've been feeling much better, thanks to your treatment plan. It's really working well for me. Doctor: That's wonderful to hear! Is there anything else you need help with? Patient: Not really, your care and services have been fantastic. However, I did want to mention that the nursing staff seemed a bit overwhelmed and weren't very attentive during my stay. Doctor: I'm sorry to hear that. I'll make sure to bring this up with the department to improve the situation. Your feedback is very valuable. Patient: Thank you. Also, some of the hospital rooms could use a bit of updating; they weren't very comfortable. Doctor: I apologize for any inconvenience. We are actively working on upgrading our facilities. Patient: I appreciate that. On a positive note, I was pleasantly surprised by how affordable my treatment was, and my insurance covered a good portion of it. Doctor: I'm glad the financial aspect was manageable. If there's anything else you need, just let me know. Patient: Thank you, Doctor. You've been very helpful."
            },
            "assistant": {
                "enrichmentResult": [
                {
                    "domain": "SENTIMENT:DoctorServices",
                    "reasoning": "The patient expresses satisfaction with the doctor's treatment and care, stating, 'your care and services have been fantastic.'",
                    "value": "POSITIVE"
                },
                {
                    "domain": "SENTIMENT:StaffServices",
                    "reasoning": "The patient mentions that the nursing staff seemed 'a bit overwhelmed and weren't very attentive.'",
                    "value": "NEGATIVE"
                },
                {
                    "domain": "SENTIMENT:HospitalFacilities",
                    "reasoning": "The patient notes that some of the hospital rooms could use updating and 'weren't very comfortable.'",
                    "value": "NEGATIVE"
                },
                {
                    "domain": "SENTIMENT:CostInsurance",
                    "reasoning": "The patient was 'pleasantly surprised by how affordable my treatment was' and mentions insurance coverage as a positive aspect.",
                    "value": "POSITIVE"
                }
                ]
       }
      }
    ]
   }
    
    CONVERSATIONAL_DATA_OUTPUT_KEY="enrichmentResult"

    # List of use cases for conversational data enrichment
    CONVERSATIONAL_DATA_ENRICHMENT_USE_CASES = {
        "SENTIMENT":SENTIMENT_ENRICHMENT_MODEL_INSTRUCTIONS, 
        "SDOH":SDOH_ENRICHMENT_MODEL_INSTRUCTIONS
    }
    
    FHIR_RESOURCES_CONFIG=dict(
                    Observation = FHIRResourceTransformConfig(
                        properties = [
                            "id", "resourceType","status", "extension", "category", "code", "subject", 
                            "effectiveDateTime", "valueQuantity"
                        ]
                    ),
                    Condition = FHIRResourceTransformConfig(
                        properties = [
                            "id","resourceType", "extension", "clinicalStatus", "verificationStatus", "category", 
                            "code", "subject", "onsetDateTime"
                        ]
                    )
                )